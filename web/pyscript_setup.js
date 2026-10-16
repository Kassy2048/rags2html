/** This script is needed to load PyScript from different locations. */

(function() {
    /* Root URL that contains the PyScript scripts */
    const PYSCRIPT_ROOT = 'https://pyscript.net/releases/2026.7.3/';
    /* URL to the interpreter to use (leave empty to use the default) */
    const INTERPRETER = '';

    function insertAfter(newNode, referenceNode) {
        const parentNode = referenceNode.parentElement;
        const nextNode = referenceNode.nextSibling;
        if(nextNode == null) {
            return parentNode.appendChild(newNode);
        } else {
            return parentNode.insertBefore(newNode, nextNode);
        }
    }

    const thisScript = document.head.querySelector('script[src$="pyscript_setup.js"]');

    /* Add the CSS file */
    const css = document.createElement('link');
    css.rel = 'stylesheet';
    css.href = PYSCRIPT_ROOT + 'core.css';
    insertAfter(css, thisScript);

    /* Add the imports map */
    const importmap = document.createElement('script');
    importmap.type = 'importmap';
    importmap.textContent = `{
      "imports": {
        "pyscript/core": "${PYSCRIPT_ROOT}core.js"
      }
    }`;
    insertAfter(importmap, css);

    /* Add the PyScript configuration */
    const pyConfig = document.createElement('py-config');
    pyConfig.textContent = `
terminal = false
packages = ["cryptography"]
${INTERPRETER === '' ? '#' : ''}interpreter = "${INTERPRETER}"
#TODO [files]
#TODO "./rags2html.zip" = "./*"
    `;
    document.body.insertBefore(pyConfig, document.body.firstChild);

    /* Add our main module script (this needs to be done after adding the imports map) */
    const mainModule = document.createElement('script');
    mainModule.type = 'module';
    mainModule.src = 'main_module.js';
    insertAfter(mainModule, importmap);

})();