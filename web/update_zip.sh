#!/bin/bash -e

TEMP_FOLDER=".rags2html.zip"
ROOT_FOLDER=".."
ZIP_FNAME="rags2html.zip"

TMP_ZIP_FNAME="${ZIP_FNAME}.tmp"

ABS_TEMP_FOLDER=`realpath $TEMP_FOLDER`
ABS_FILE_PATH=`realpath ./$TMP_ZIP_FNAME`

echo "Copying files to temporary folder..."

rm -rf "$TEMP_FOLDER" "$ABS_FILE_PATH"
mkdir "$TEMP_FOLDER"

pushd "$ROOT_FOLDER" > /dev/null

# Only include files part of the repository
git ls-files *.py vendor | xargs -I{} cp -a --parents {} "$ABS_TEMP_FOLDER"

popd > /dev/null

echo "Zipping files..."

pushd $TEMP_FOLDER > /dev/null

zip -qr "$ABS_FILE_PATH" *

popd > /dev/null

rm -rf "$TEMP_FOLDER"

# Check if the file content is different from the old one
if [ -f "$ZIP_FNAME" ]; then
    # List all the files in the zip files and only keep their CRC (7) and path (8)
    unzip -v "$ZIP_FNAME" | awk '/Defl|Stored/ {print $7, $8}' | sort > "$ZIP_FNAME.lst"
    unzip -v "$TMP_ZIP_FNAME" | awk '/Defl|Stored/ {print $7, $8}' | sort > "$TMP_ZIP_FNAME.lst"

    set +e
    diff -q "$ZIP_FNAME.lst" "$TMP_ZIP_FNAME.lst" > /dev/null
    same_content=$?
    set -e

    rm "$ZIP_FNAME.lst" "$TMP_ZIP_FNAME.lst"

    if [ $same_content -eq 0 ]; then
        echo "Same content as before, no need to update."
        rm "$TMP_ZIP_FNAME"
        exit 0
    fi

    echo "Replacing old version of $ZIP_FNAME..."
fi

mv "$TMP_ZIP_FNAME" "$ZIP_FNAME"
