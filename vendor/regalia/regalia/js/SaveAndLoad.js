var SavedGames = {
    titleForSave: function () {
        return GameController.title();
    },
    keyForIndex: function () {
        return this.titleForSave() + '-Saves';
    },
    keyForSave: function (n) {
        return this.titleForSave() + '-Save' + n;
    },
    getIndex: function () {
        var rawIndex = localStorage.getItem(this.keyForIndex());
        if (rawIndex) {
            return JSON.parse(rawIndex)
        } else {
            this.reset();
            return {};
        }
    },
    getSortedSaves: function () {
        var parsedIndex = this.getIndex();
        return Object.keys(parsedIndex).sort(function (a, b) {
            return parseInt(b, 10) - parseInt(a, 10);
        }).map(function (id) {
            return parsedIndex[id];
        });
    },
    getSave: function (id) {
        return JSON.parse(localStorage.getItem(this.keyForSave(id)));
    },
    nextSaveId: function () {
        var lastSave = this.getSortedSaves()[0];
        return (lastSave ? lastSave.id : 0) + 1;
    },
    createSave: function (id, name, date, gameData) {
        var savedGames = this.getIndex();
        savedGames[id] = {
            id: id,
            name: name,
            date: date
        };

        let mainText = $("#MainText").html();
        if(mainText.length > 100000) {
            // Do not store more than 100K characters (~10KB after compression)
            const pos = mainText.indexOf('<hr>', mainText.length - 100000);
            const oldLength = mainText.length;
            if(pos == -1) {
                // TODO Try to store something that does not break the DOM tree
                mainText = '';
            } else {
                mainText = mainText.slice(pos + 4);
            }
            console.log("Text history truncated to " + mainText.length + " (from " + oldLength + ")");
        }

        // Compress the main text
        let zData = LZMA.compress(mainText, 1);
        if(zData.length & 1) zData.push(0);  // Pad with 0 to get a multiple of 2 bytes
        zData = new Int8Array(zData);
        // Convert the result to an UTF-16 string (2 bytes per characters)
        const zText = String.fromCharCode.apply(null, new Uint16Array(zData.buffer));

        persistKeyValue(this.keyForSave(id), JSON.stringify({
            id: id,
            name: name,
            date: date,
            gameData: gameData,
            cheatFreezes: window.cheatFreezes,
            zMainText: zText,
            currentImage: Globals.currentImage,
        }));

        persistKeyValue(this.keyForIndex(), JSON.stringify(savedGames));
    },
    destroySave: function (id) {
        var savedGames = this.getIndex();
        delete savedGames[id];
        localStorage.removeItem(this.keyForSave(id));
        persistKeyValue(this.keyForIndex(), JSON.stringify(savedGames));
    },
    reset: function () {
        var rawIndex = localStorage.getItem(this.keyForIndex());
        if (rawIndex) {
            var saveKeys = Object.keys(JSON.parse(rawIndex));
            for (var i = 0; i < saveKeys.length; i++) {
                localStorage.removeItem(this.keyForSave(saveKeys[i]));
            }
        }
        persistKeyValue(this.keyForIndex(), JSON.stringify({}));
    },
    import: function (newSaves) {
        var savedGames = this.getIndex();
        for (var i = 0; i < newSaves.length; i++) {
            var newSave = newSaves[i];
            savedGames[newSave.id] = {
                id: newSave.id,
                name: newSave.name,
                date: newSave.date
            };
            persistKeyValue(this.keyForSave(newSave.id), JSON.stringify(newSave));
        }
        persistKeyValue(this.keyForIndex(), JSON.stringify(savedGames));
    },

    saveDataFor: function (game) {
      return DeepDiff.diff(OriginalGame, game, {prefilter: (path, key) => {
            // Ignore properties that cannot change
            switch(key) {
                case 'PassCommands':
                case 'FailCommands':
                case 'Conditions':
                case 'EnhInputData':
                case 'cloneForDiff':  // function, do not compare
                    return true;
            }
            return false;
        }});
    },

    applySaveToGame: function (game, savedGame) {
        let changes = savedGame.gameData;
        // Check for old save where changes were stringified for no good reason
        if(typeof changes == 'string') changes = JSON.parse(savedGame.gameData);
        var orderedChanges = orderChanges(changes);

        for (var i = 0; i < orderedChanges.length; i++) {
            DeepDiff.applyChange(TheGame, true, orderedChanges[i]);
        }

        if(savedGame.zMainText !== undefined) {
            let zData = new Uint16Array(savedGame.zMainText.length)
            for(let i = 0 ; i < zData.length ; ++i) {
                zData[i] = savedGame.zMainText.charCodeAt(i);
            }
            const mainText = LZMA.decompress(new Int8Array(zData.buffer));
            $("#MainText").html(mainText);
            GameUI.setDarkMode(Settings.darkMode);
        }
    },

    importRSV: async function(buffer) {
        // openssl enc -aes-256-cbc -nosalt -d -in rags_save.rsv -K 'B4BDC259B1104A6531F8109C851BCF9AD09BDD208851C9CBAB782AEC356CC1E3' -iv '31F8109C851BCF9A203D6C71A7BD1487'
        const aes_key = new Uint8Array([
                0xB4, 0xBD, 0xC2, 0x59, 0xB1, 0x10, 0x4A, 0x65,
                0x31, 0xF8, 0x10, 0x9C, 0x85, 0x1B, 0xCF, 0x9A,
                0xD0, 0x9B, 0xDD, 0x20, 0x88, 0x51, 0xC9, 0xCB,
                0xAB, 0x78, 0x2A, 0xEC, 0x35, 0x6C, 0xC1, 0xE3]);
        const aes_iv = new Uint8Array([
                0x31, 0xF8, 0x10, 0x9C, 0x85, 0x1B, 0xCF, 0x9A,
                0x20, 0x3D, 0x6C, 0x71, 0xA7, 0xBD, 0x14, 0x87]);

        let data;
        try {
            console.log(`Decrypting file content...`);
            const key = await window.crypto.subtle.importKey("raw", aes_key, "AES-CBC", false, ["decrypt"]);
            data = await window.crypto.subtle.decrypt({name: "AES-CBC", iv: aes_iv}, key, buffer);
        } finally {
            // Free memory
            buffer = '';
            e = {};
            if(data === undefined) alert(`Decryption failed!`);
        }
        // console.debug(data);

        let root;
        try {
            console.log(`Extracting data...`);
            $('.import-menu-status').html('Extracting RSV file...');
            // Let the HTML update
            await new Promise(r => setTimeout(r, 0));
            let percent = -1;
            root = parseNrbf(data, async (pos, size, step) => {
                if(step > 0) --step;
                const new_percent = Math.floor(pos * 90 / size + step * 5);
                if(new_percent != percent) {
                    percent = new_percent;
                    $('.import-menu-status').text(`Extracting RSV file (${percent}%)`);
                    // Let the HTML update
                    await new Promise(r => setTimeout(r, 0));
                }
            });
        } finally {
            // Free memory
            data = '';
            if(root === undefined) alert(`Extraction failed!`);
        }

        console.debug(root);
        return root;
    },

    applyRsvToGame: function (_game, root) {
        // FIXME We should only change "_game" but we keep touching the global
        //       variable "TheGame" instead (because we use the Finder)
        console.log(`Importing data...`);

        const VarType_map = {
            0: "VT_UNINITIALIZED",
            1: "VT_NUMBER",
            2: "VT_STRING",
            3: "VT_DATETIME",
            4: "VT_NUMBERARRAY",
            5: "VT_STRINGARRAY",
            6: "VT_DATETIMEARRAY",
        };

        const Direction_map = {
            0: "Empty",
            1: "North",
            2: "South",
            3: "East",
            4: "West",
            5: "Up",
            6: "Down",
            7: "NorthEast",
            8: "NorthWest",
            9: "SouthWest",
            10: "SouthEast",
            11: "In",
            12: "Out",
        };

        const CharGender_map = {
            0: "Male",
            1: "Female",
            2: "Other",
        };

        const TimerType_map = {
            0: "TT_RUNALWAYS",
            1: "TT_LENGTH",
        };

        const LocationType_map = {
            0: "LT_NULL",
            1: "LT_IN_OBJECT",
            2: "LT_ON_OBJECT",
            3: "LT_ROOM",
            4: "LT_PLAYER",
            5: "LT_CHARACTER",
            6: "LT_PORTAL",
        };

        const ActionInputType_map = {
            0: "None",
            1: "Object",
            2: "Character",
            3: "ObjectOrCharacter",
            4: "Text",
            5: "Custom",
            6: "Inventory",
        };

        const CheckType_map = {
            0: "CT_Uninitialized",
            1: "And",
            2: "Or",
        };

        function enumValue(_enum) {
            return (typeof(_enum) == 'object' && 'value__' in _enum)
                    ? _enum.value__ : _enum;
        }

        function VarType(vartype) {
            return VarType_map[enumValue(vartype)] || VarType_map[0];
        }

        function Direction(direction) {
            return Direction_map[enumValue(direction)] || Direction_map[0];
        }

        function CharGender(gender) {
            return CharGender_map[enumValue(gender)] || CharGender_map[0];
        }

        function TimerType(ttype) {
            return TimerType_map[enumValue(ttype)] || exportTimerType[0];
        }

        function LocationType(location) {
            return LocationType_map[enumValue(location)] || LocationType_map[0];
        }

        function ActionInputType(aitype) {
            return ActionInputType_map[enumValue(aitype)] || ActionInputType_map[0];
        }

        function CheckType(ctype) {
            return CheckType_map[enumValue(ctype)] || CheckType_map[0];
        }

        function Guid(guid) {
            // "n >>> 0" convert the number to unsigned
            function hex2(n) {
                return (n >>> 0).toString(16).padStart(2, '0').slice(-2);
            }
            function hex4(n) {
                return (n >>> 0).toString(16).padStart(4, '0').slice(-4);
            }
            function hex8(n) {
                return (n >>> 0).toString(16).padStart(8, '0').slice(-8);
            }

            return hex8(guid._a) + '-'
                    + hex4(guid._b) + '-' + hex4(guid._c) + '-'
                    + hex2(guid._d) + hex2(guid._e) + '-'
                    + hex2(guid._f) + hex2(guid._g) + hex2(guid._h)
                    + hex2(guid._i) + hex2(guid._j) + hex2(guid._k);
        }

        function DateTime(dt) {
            // Convert from DateTime representation
            // <https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-nrbf/f05212bd-57f4-4c4b-9d98-b84c7c658054>
            // const m = moment('01/01/0001 12:00:00', "DD/MM/YYYY hh:mm:ss");
            const m = moment('01/01/0001 00:00:00', "DD/MM/YYYY hh:mm:ss");
            const seconds = dt.ticks / 10000000n;
            const nSeconds = Number(seconds);
            if(seconds != BigInt(nSeconds)) {
                console.debug(`Precision lost: ${seconds} => ${nSeconds}`);
            }
            m.add(nSeconds, 'seconds');
            // FIXME The date it always off by 3039 seconds plus the DST offset
            return m.format(DateTimes.defaultDateFormat);
        }

        function adaptText(str) {
            return str.replaceAll('\n', '<br>').replaceAll('\r', '');
        }

        function adaptText_nobr(str) {
            return str.replaceAll('\r', '');
        }

        let success = true;

        const refGame = JSON.parse(JSON.stringify(_game));

        /** This function is just an helper to make sure there is no typo in RSV
         * conversion code.
         */
        function update(gameObject, gameField, object, objectField, convertFunc) {
            if(objectField === undefined || objectField.length == 0) {
                objectField = gameField;
            }

            if(!(gameField in gameObject)) {
                console.warn(gameObject, gameField, object, objectField);
                throw new Error(`${gameField} not in game object ${gameObject}`);
            }
            if(!(objectField in object)) {
                console.warn(gameObject, gameField, object, objectField);
                throw new Error(`${objectField} not in save object ${object}`);
            }

            if(convertFunc !== undefined) {
                gameObject[gameField] = convertFunc(object[objectField], object, objectField, gameObject, gameField);
            } else {
                gameObject[gameField] = object[objectField];
            }
        }

        function updateAction(gameAction, action) {
            update(gameAction, 'bActive', action);
            update(gameAction, 'bConditionFailOnFirst', action);
            update(gameAction, 'overridename', action, 'nameoverride');
            update(gameAction, 'actionparent', action);
            update(gameAction, 'InputType', action, '', ActionInputType);
            update(gameAction, 'CustomChoices', action);  // array of strings
        }

        root.CharacterList.forEach(saveObj => {
            const gameObj = Finder.character(saveObj.Charname);
            if(!gameObj) {
                console.error("Cannot find character " + saveObj.Charname);
                success = false;
                return;
            }

            gameObj.CustomProperties = saveObj.CustomProperties.map(prop => {
                return SetupCustomPropertyData([adaptText(prop.Name), adaptText(prop.Value)]);
            });

            saveObj.Actions.forEach(action => {
                const gameAction = Finder.action(gameObj.Actions, action.name);
                if(!gameAction) {
                    console.error("Cannot find action " + action.name + " for character " + saveObj.Charname);
                    success = false;
                    return;
                }

                updateAction(gameAction, action);
            });

            // XXX Charname can change using text attribute, but that's also the character key,
            //     so it should be constant!?
            // update(gameObj, 'Charname', saveObj);
            update(gameObj, 'CharGender', saveObj, '', CharGender);
            update(gameObj, 'CharPortrait', saveObj);
            update(gameObj, 'CharnameOverride', saveObj);
            update(gameObj, 'CurrentRoom', saveObj);
            update(gameObj, 'Description', saveObj, '', adaptText);
            update(gameObj, 'bAllowInventoryInteraction', saveObj);
            update(gameObj, 'bEnterFirstTime', saveObj);
            update(gameObj, 'bLeaveFirstTime', saveObj);
        });

        root.ObjectList.forEach(saveObj => {
            const uid = Guid(saveObj.UniqueIdentifier);
            const gameObj = Finder.object(uid);
            if(!gameObj) {
                console.error("Cannot find object " + uid + " (" + saveObj.name + ")");
                success = false;
                return;
            }

            gameObj.CustomProperties = saveObj.CustomProperties.map(prop => {
                return SetupCustomPropertyData([adaptText(prop.Name), adaptText(prop.Value)]);
            });

            saveObj.Actions.forEach(action => {
                const gameAction = Finder.action(gameObj.Actions, action.name);
                if(!gameAction) {
                    console.error("Cannot find action " + action.name + " for object " + saveObj.name);
                    success = false;
                    return;
                }

                updateAction(gameAction, action);
            });

            update(gameObj, 'bCarryable', saveObj);
            update(gameObj, 'bContainer', saveObj);
            update(gameObj, 'bEnterFirstTime', saveObj);
            update(gameObj, 'bEnterable', saveObj);
            if('bImportant' in saveObj) update(gameObj, 'bImportant', saveObj);
            update(gameObj, 'bLeaveFirstTime', saveObj);
            update(gameObj, 'bLockable', saveObj);
            update(gameObj, 'bLocked', saveObj);
            update(gameObj, 'bOpen', saveObj);
            update(gameObj, 'bOpenable', saveObj);
            update(gameObj, 'bReadable', saveObj);
            update(gameObj, 'bVisible', saveObj);
            update(gameObj, 'bWearable', saveObj);
            update(gameObj, 'bWorn', saveObj);
            update(gameObj, 'dWeight', saveObj);
            update(gameObj, 'description', saveObj, '', adaptText);
            update(gameObj, 'locationname', saveObj);
            update(gameObj, 'locationtype', saveObj, '', LocationType);
            update(gameObj, 'name', saveObj, '', adaptText);
            update(gameObj, 'preposition', saveObj);
            update(gameObj, 'sdesc', saveObj, '', adaptText);
        });

        root.RoomList.forEach(saveObj => {
            const uid = Guid(saveObj.UniqueID);
            const gameObj = Finder.room(uid);
            if(!gameObj) {
                console.error("Cannot find room " + uid + " (" + saveObj.Name + ")");
                success = false;
                return;
            }

            gameObj.CustomProperties = saveObj.CustomProperties.map(prop => {
                return SetupCustomPropertyData([adaptText(prop.Name), adaptText(prop.Value)]);
            });

            saveObj.Actions.forEach(action => {
                const gameAction = Finder.action(gameObj.Actions, action.name);
                if(!gameAction) {
                    console.error("Cannot find action " + action.name + " for room " + saveObj.Name);
                    success = false;
                    return;
                }

                updateAction(gameAction, action);
            });

            update(gameObj, 'Description', saveObj, '', adaptText);
            update(gameObj, 'Name', saveObj, '', adaptText);
            update(gameObj, 'RoomPic', saveObj);
            update(gameObj, 'SDesc', saveObj, '', adaptText);
            update(gameObj, 'bEnterFirstTime', saveObj);
            update(gameObj, 'bLeaveFirstTime', saveObj);

            gameObj.Exits = [];
            saveObj.Exits.forEach(exit => {
                gameObj.Exits.push(SetupExitData([
                        Direction(exit.Direction),
                        exit.bActive,
                        exit.DestinationRoom,
                        exit.PortalObjectName]));
            });
        });

        root.TimerList.forEach(saveObj => {
            const gameObj = Finder.timer(saveObj.Name);
            if(!gameObj) {
                console.error("Cannot find timer " + saveObj.Name);
                success = false;
                return;
            }

            gameObj.CustomProperties = saveObj.CustomProperties.map(prop => {
                return SetupCustomPropertyData([adaptText(prop.Name), adaptText(prop.Value)]);
            });

            saveObj.Actions.forEach(action => {
                const gameAction = Finder.action(gameObj.Actions, action.name);
                if(!gameAction) {
                    console.error("Cannot find action " + action.name + " for timer " + saveObj.Name);
                    success = false;
                    return;
                }

                updateAction(gameAction, action);
            });

            update(gameObj, 'Active', saveObj);
            update(gameObj, 'LiveTimer', saveObj);
            update(gameObj, 'TType', saveObj, '', TimerType);
            update(gameObj, 'TimerSeconds', saveObj);
            update(gameObj, 'TurnNumber', saveObj);
            // update(gameObj, 'curtickcount', saveObj);
            if('curtickcount' in saveObj) console.debug("Found curtickcount in save object", saveObj);
            gameObj.curtickcount = 0;
        });

        root.VariableList.forEach(saveObj => {
            const gameObj = Finder.variable(saveObj.varname);
            if(!gameObj) {
                console.error("Cannot find variable " + saveObj.varname);
                success = false;
                return;
            }

            gameObj.CustomProperties = saveObj.CustomProperties.map(prop => {
                return SetupCustomPropertyData([adaptText(prop.Name), adaptText(prop.Value)]);
            });

            if(gameObj.vartype.endsWith("ARRAY")) {
                const stringArray = gameObj.vartype == "VT_STRINGARRAY";
                const numberArray = gameObj.vartype == "VT_NUMBERARRAY";
                gameObj.VarArray = saveObj.VarArray.map(el => {
                    if(Array.isArray(el)) {
                        if(stringArray) return el.map(adaptText_nobr);
                        if(numberArray) return el.map(Number);
                        return el.map(DateTime);
                    } else {
                        if(stringArray) return adaptText(el);
                        if(numberArray) return Number(el);
                        return DateTime(el);
                    }
                });
            }
            update(gameObj, 'dNumType', saveObj);
            update(gameObj, 'sString', saveObj, '', adaptText);
            if(gameObj.vartype == "VT_DATETIME") {
                // Only update if the variable should contain a DateTime as conversion is not
                // accurate so it creates too much deltas with the original game data
                update(gameObj, 'dtDateTime', saveObj, '', DateTime);
            }
        });

        root.StatusBarList.forEach(saveObj => {
            const gameObj = TheGame.StatusBarItems.find((item) => {
                return item.Name == saveObj.Name;
            });
            if(!gameObj) {
                console.error("Cannot find status bar item " + saveObj.Name);
                success = false;
                return;
            }

            update(gameObj, 'bVisible', saveObj);
        });

        {
            const saveObj = root.ThePlayer;
            const gameObj = TheGame.Player;

            gameObj.CustomProperties = saveObj.CustomProperties.map(prop => {
                return SetupCustomPropertyData([adaptText(prop.Name), adaptText(prop.Value)]);
            });

            saveObj.Actions.forEach(action => {
                const gameAction = Finder.action(gameObj.Actions, action.name);
                if(!gameAction) {
                    console.error("Cannot find action " + action.name + " for player");
                    success = false;
                    return;
                }

                updateAction(gameAction, action);
            });

            gameObj.CurrentRoom = saveObj.CurrentRoom ? Guid(saveObj.CurrentRoom.UniqueID) : null;
            update(gameObj, 'Description', saveObj, '', adaptText);
            update(gameObj, 'Name', saveObj);
            update(gameObj, 'PlayerGender', saveObj, '', CharGender);
            update(gameObj, 'PlayerPortrait', saveObj);
        }

        function dumpPath(path) {
            return path.join('.');
        }

        function dumpChanges(a, b, path) {
            const type_a = typeof(a), type_b = typeof(b);
            if(type_a != type_b) {
                console.debug(`${dumpPath(path)}: ${JSON.stringify(a)} => ${JSON.stringify(b)}`);
                return;
            }

            switch(type_a) {
                case 'string':
                case 'boolean':
                case 'number':
                    if(a != b) console.debug(`${dumpPath(path)}: ${JSON.stringify(a)} => ${JSON.stringify(b)}`);
                    break;

                case 'object': {
                    const array_a = Array.isArray(a);
                    const array_b = Array.isArray(b);
                    if(array_a != array_b) {
                        console.debug(`${dumpPath(path)}: ${JSON.stringify(a)} => ${JSON.stringify(b)}`);
                    } else if(array_a) {
                        const count = Math.max(a.length, b.length);
                        const name = path.length > 0 ? path.at(-1) : '';
                        path.pop();
                        for(let i = 0 ; i < count ; ++i) {
                            path.push(`${name}[${i}]`);
                            if(i >= a.length) {
                                console.debug(`${dumpPath(path)}: missing => ${JSON.stringify(b)}`);
                            } else if(i >= b.length) {
                                console.debug(`${dumpPath(path)}: ${JSON.stringify(a)} => missing`);
                            } else {
                                dumpChanges(a[i], b[i], path);
                            }
                            path.pop();
                        }
                        if(name.length > 1) path.push(name);
                    } else if(a === null || b === null) {
                        if(a !== null || b !== null) {
                            console.debug(`${dumpPath(path)}: ${JSON.stringify(a)} => ${JSON.stringify(b)}`);
                        }
                    } else {
                        const a_keys = new Set();
                        Object.getOwnPropertyNames(a).forEach(key => {
                            a_keys.add(key);
                            path.push(key);
                            if(Object.hasOwn(b, key)) {
                                dumpChanges(a[key], b[key], path);
                            } else {
                                console.debug(`${dumpPath(path)}: ${JSON.stringify(a[key])} => missing`);
                            }
                            path.pop();
                        });
                        Object.getOwnPropertyNames(b).forEach(key => {
                            if(a_keys.has(key)) return;
                            path.push(key);
                            console.debug(`${dumpPath(path)}: missing => ${JSON.stringify(b[key])}`);
                            path.pop();
                        });
                    }

                    break;
                }

                default:
                    console.warn(`Unknown type "${type_a}" for ${dumpPath(path)}`);
            }
        }

        // Re-create the name/uid maps
        // FIXME Not needed anymore (we don't create new objects)?
        Finder.addMaps(TheGame);

        if(!success) {
            alert("Import failed. Check console for details.");
            throw new Error("Import failed.");
        }

        //dumpChanges(refGame, TheGame, []);

        console.log(`Done.`);
    },

    renameSave: function (id, name) {
        const savedGames = this.getIndex();
        savedGames[id].name = name;
        persistKeyValue(this.keyForIndex(), JSON.stringify(savedGames));

        // No need to update the name in the full save data as it is never used
        // and it takes a significant time
    },
};

function persistKeyValue(key, value) {
    try {
        localStorage.setItem(key, value);
    } catch (e) {
        if (e instanceof DOMException && e.message.match(/exceeded the quota/)) {
            alert("Save operation failed: localStorage quota exceeded.\n\nDelete some saves and try again.");
        }
        throw e;
    }
}

function pathsEqual(p1,p2) {
    return JSON.stringify(p1) == JSON.stringify(p2);
}

function orderChanges(changes) {
    var result = [];
    // Reverse the order of array deletions generated by deep-diff to get the correct result
    // See https://github.com/flitbit/diff/issues/35 and https://github.com/flitbit/diff/issues/47

    function addReversedChanges(changesToReverse) {
        changesToReverse.reverse();
        for (var i = 0; i < changesToReverse.length; i++) {
            result.push(changesToReverse[i]);
        }
    }

    var currentArrayDeletionChanges = null;
    for (var i = 0; i < changes.length; i++) {
        var change = changes[i];
        if (change.kind == "A" && change.item.kind == "D") {
            if (currentArrayDeletionChanges) {
                if (pathsEqual(currentArrayDeletionChanges[0].path, change.path)) {
                    currentArrayDeletionChanges.push(change);
                    continue;
                } else {
                    addReversedChanges(currentArrayDeletionChanges);
                    currentArrayDeletionChanges = [change];
                    continue;
                }
            } else {
                currentArrayDeletionChanges = [change];
                continue;
            }
        }

        if (currentArrayDeletionChanges) {
            addReversedChanges(currentArrayDeletionChanges);
            currentArrayDeletionChanges = null;
        }
        result.push(change);
    }

    // In case the last change was itself a delete
    if (currentArrayDeletionChanges) {
        addReversedChanges(currentArrayDeletionChanges);
        currentArrayDeletionChanges = null;
    }

    return result;
}