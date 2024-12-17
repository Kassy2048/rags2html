import { hooks } from "pyscript/core";  // from importmap

hooks.main.onReady.add(async (wrap, element) => {
    const pyscript = wrap;

    console.debug('onPyReady - BEGIN', wrap);

    document.querySelector('.howto').style.display = 'revert';

    const pyodide = pyscript.interpreter;
    const FS = pyodide.FS;
    window.FS = FS;  // DEBUG

    const fileInput = document.getElementById('file');
    const dlFile = document.getElementById('dlfile');
    const action = document.getElementById('action');
    const progress = document.querySelector('#progress');
    const progressBar = document.querySelector('#progress .value');
    const logDiv = document.getElementById('log');
    const dropzone = document.getElementById('dropzone');
    const playframe = document.getElementById('playframe');

    // FIXME Hook wrap.io.stdout instead
    pyodide.setStdout({batched: (msg) => {
        console.log(msg);
        const line = document.createElement('span');
        line.textContent = msg;
        line.style.color = 'forestgreen';
        logDiv.appendChild(line);
        logDiv.appendChild(document.createElement('br'));
        logDiv.scrollTop = logDiv.scrollHeight;
    }});

    // FIXME Hook wrap.io.stderr instead
    pyodide.setStderr({batched: (msg) => {
        console.log("%c" + msg, "color: salmon");
        const line = document.createElement('span');
        line.textContent = msg;
        line.style.color = 'red';
        line.style.fontWeight = 'bold';
        logDiv.appendChild(line);
        logDiv.appendChild(document.createElement('br'));
        logDiv.scrollTop = logDiv.scrollHeight;
    }});

    function syncfs(populate) {
        return new Promise((resolve, reject) => {
            FS.syncfs(populate, (err) => {
                if(err) reject(err);
                else resolve();
            });
        });
    }

    // FIXME Tell PyScript to download and extract it in the py-config section instead
    let zipResponse = await fetch("rags2html.zip");
    let zipBinary = await zipResponse.arrayBuffer();
    pyodide.unpackArchive(zipBinary, "zip");

    function fileExist(path) {
        return FS.analyzePath(path).exists;
    }

    function delTree(path, keepRoot) {
        if(!fileExist(path)) return;

        const stat = FS.stat(path);
        if(FS.isDir(stat.mode)) {
            FS.readdir(path).forEach((entry) => {
                if(entry == '.' || entry == '..') return;
                delTree(path + '/' + entry, false);
            });
            if(!keepRoot) FS.rmdir(path);
        } else if(FS.isFile(stat.mode)) {
            FS.unlink(path);
        }
    }

    window.convertProgress = function(full_progress, task, task_progress, task_total) {
        const percent = Math.floor(full_progress * 100.0);
        let label = percent + '%';
        if(task !== undefined) {
            label += ' - ' + task;
            if(task_progress > -1 && task_total !== undefined) {
                label += ` (${task_progress} / ${task_total})`;
            }
        }

        progress.dataset.label = label;
        progressBar.style.width = percent + '%';
    };

    const baseDir = '/rags';
    FS.mkdirTree(baseDir);
    // Using IDBFS to prevent OOM with big files?
    // XXX Not working, emscripten still needs to have the whole FS in memory...
    //FS.mount(FS.filesystems.IDBFS, {}, baseDir);

    let busy = false;

    fileInput.addEventListener('click', (e) => {
        // Reset the field value so that the "change" event is triggered
        // if the user selected the same file again
        fileInput.value = null;
    });

    fileInput.addEventListener('change', async (e) => {
        console.log(e);
        if(busy) return;

        if(fileInput.files.length == 0) return;  // Happens on cancel
        if(fileInput.files.length > 1) {
            alert("Only select one file.");
            return;
        }

        const file = fileInput.files[0];
        if(!file.name.toLowerCase().endsWith('.rag')) {
            alert("Only select RAGS files.");
            return;
        }
        convertFile(file);
    });

    async function convertFile(file) {
        if(busy) return;

        busy = true;
        fileInput.disabled = true;
        action.disabled = true;

        try {
            const showInfo = action.value == 'info';

            convertProgress(0, 'Fetching game file...');

            // Reset
            dlFile.style.display = 'none';
            window.URL.revokeObjectURL(dlFile.href);
            delTree(baseDir, true);
            logDiv.innerHTML = '';

            const start = performance.now();
            const filePath = baseDir + '/' + file.name;
            // Faster to call arrayBuffer() than streaming the file content
            const data = await file.arrayBuffer();
            FS.writeFile(filePath, new Uint8Array(data));
            await syncfs(false);
            console.debug(`Imported file in ${performance.now() - start} ms`);

            convertProgress(0.1, 'Fetching game file...');

            await pyodide.runPythonAsync(`
import os
import zipfile
import shutil
import time

import js

import rags2html

fpath = "${filePath.replaceAll(/[\\"]/g, "\\$&")}"
outPath = os.path.splitext(fpath)[0]

lastProgress = None
def progress(full_progress, task, task_progress, task_total=None):
    # Only update the UI every 100 ms to reduce the load
    global lastProgress
    now = time.monotonic()
    if lastProgress is not None and now - lastProgress < 0.1:
        return
    lastProgress = now

    js.convertProgress(0.1 + full_progress * 0.8, task, task_progress, task_total);

await rags2html.main(['rags2html', fpath ${showInfo ? ", '--info'" : ""}], progress=progress)

# Make some free space
os.unlink(fpath)

if os.path.exists(os.path.join(outPath, 'regalia', 'game', 'Game.js')):
    print("Writing ZIP file...")
    js.convertProgress(0.9, 'Writing ZIP file...', -1)

    compressExt = set(('.html', '.js', '.json', '.css', '.txt'))

    def zipTree(zip, path, basePath):
        if os.path.isdir(path):
            for entry in os.listdir(path):
                zipTree(zip, os.path.join(path, entry), basePath)
        elif os.path.isfile(path):
            compression = zipfile.ZIP_STORED
            if os.path.splitext(path)[1].lower() in compressExt:
                # Only compress text files
                compression=zipfile.ZIP_DEFLATED
            
            zip.write(path, arcname=os.path.relpath(path, basePath), compress_type=compression)

    with zipfile.ZipFile(outPath + '.zip', mode='w') as zip:
        zipTree(zip, outPath, os.path.dirname(outPath))
        zip.comment = (('Converted from "%s" with Rags2Html.\\n'
                + "Rags2Html repository: https://github.com/Kassy2048/rags2html\\n"
                + "Using Regalia: https://github.com/selectivepaperclip/regalia")
                    % (os.path.basename(fpath))).encode('utf-8')

    js.resultPath = outPath + '.zip'
else:
    js.resultPath = False

# Cleanup
shutil.rmtree(outPath, ignore_errors=True)
`);
            await syncfs(false);

            if(showInfo) {
                convertProgress(1.0, `Info extracted in ${Math.round((performance.now() - start) / 1000)} seconds`);
            } else if(resultPath !== false) {
                console.log('Success!');
                convertProgress(0.95, 'Downloading ZIP file...', -1);
                dlFile.download = resultPath.slice(resultPath.lastIndexOf('/') + 1);
                dlFile.href = window.URL.createObjectURL(new Blob([FS.readFile(resultPath)],
                        { type: 'application/zip'}));
                dlFile.style.display = 'unset';
                console.debug(`Conversion took ${performance.now() - start} ms`);
                convertProgress(1.0, `Done in ${Math.round((performance.now() - start) / 1000)} seconds`);
                dlFile.click();
            } else {
                console.log('Conversion failed');
                convertProgress(1.0, 'Conversion failed!');
            }
        } finally {
            fileInput.disabled = false;
            action.disabled = false;
            busy = false;
        }
    }

    // Drag'n'drop

    function dnd_files(e) {
        let files = [];
        if(e.dataTransfer.items) {
            // Use DataTransferItemList interface to access the file(s)
            [...e.dataTransfer.items].forEach((item, i) => {
                // If dropped items aren't files, reject them
                if (item.kind === "file") {
                    files.push(item.getAsFile());
                }
            });
        } else {
            // Use DataTransfer interface to access the file(s)
            [...ev.dataTransfer.files].forEach((file, i) => {
                files.push(file);
            });
        }
        return files;
    }

    document.addEventListener('drop', async (e) => {
        dropzone.style.display = 'none';

        e.preventDefault();
        console.log(e);

        if(busy) {
            alert("Wait for current conversion to complete.");
            return;
        }

        const files = dnd_files(e);
        if(files.length == 0) {
            alert("Only drag files on this page.");
            return;
        }
        if(files.length > 1) {
            alert("Only drag one file on this page.");
            return;
        }

        const file = files[0];
        if(!file.name.toLowerCase().endsWith('.rag')) {
            alert("Only drag RAGS files on this page.");
            return;
        }

        // Replace input file value with this file (this does not trigger the "change" event)
        const dt = new DataTransfer();
        dt.items.add(file);
        fileInput.files = dt.files;

        convertFile(file);
    });

    document.addEventListener('dragover', (e) => {
        e.preventDefault();
    });

    // Show/hide drop zone based on dragging
    document.addEventListener('dragenter', (e) => {
        if(busy) return;
        if(e.relatedTarget === null) {
            dropzone.style.display = 'inherit';
        }
    });
    document.addEventListener('dragleave', (e) => {
        if(busy) return;
        if(e.relatedTarget === null) {
            dropzone.style.display = 'none';
        }
    });

    // Persist settings

    if(window.localStorage !== undefined) {
        const value = window.localStorage['rags2html-action'];
        if(value !== undefined) action.value = value;

        action.addEventListener('change', (e) => {
            window.localStorage['rags2html-action'] = action.value;
        });
    }

    console.debug('onPyReady - END');
});
