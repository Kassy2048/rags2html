var Finder = {
    action: function(actions, name) {
        var lowercaseActionName = name.trim().toLowerCase();
        if(actions.NameMap !== undefined) {
            return actions.NameMap[lowercaseActionName];
        }
        console.debug("No NameMap for actions", actions, name);
        return actions.find(function (action) {
            return action.name.trim().toLowerCase() === lowercaseActionName;
        });
    },
    timer: function(timerName) {
        var lowercaseTimerName = timerName.trim().toLowerCase();
        if(TheGame.Timers.NameMap !== undefined) {
            return TheGame.Timers.NameMap[lowercaseTimerName];
        }
        console.debug("No NameMap for timers", timerName);
        return TheGame.Timers.find(function (timer) {
            return timer.Name.trim().toLowerCase() === lowercaseTimerName;
        });
    },
    variable: function(variableName) {
        variableName = variableName.trim();
        if (variableName.indexOf("(") > -1) {
            variableName = variableName.substring(0, variableName.indexOf("("));
        }

        var lowercaseVariableName = variableName.toLowerCase();
        if(TheGame.Variables.NameMap !== undefined) {
            return TheGame.Variables.NameMap[lowercaseVariableName];
        }
        console.debug("No NameMap for variables", variableName);
        return TheGame.Variables.find(function (variable) {
            return variable.varname.trim().toLowerCase() === lowercaseVariableName;
        });
    },
    object: function(uidOrName) {
        if (!uidOrName) {
            return null;
        }
        uidOrName = uidOrName.trim();

        if(TheGame.Objects.UidMap !== undefined) {
            const obj = TheGame.Objects.UidMap[uidOrName];
            if(obj !== undefined) return obj;
        } else {
            console.debug("No UidMap for objects", uidOrName);
            for (var i = 0; i < TheGame.Objects.length; i++) {
                if (TheGame.Objects[i].UniqueIdentifier === uidOrName) {
                    return TheGame.Objects[i];
                }
            }
        }

        var lowercaseObjectName = uidOrName.toLowerCase();
        if(TheGame.Objects.NameMap !== undefined) {
            return TheGame.Objects.NameMap[lowercaseObjectName];
        }
        console.debug("No NameMap for objects", uidOrName);
        for (var j = 0; j < TheGame.Objects.length; j++) {
            if (TheGame.Objects[j].name && TheGame.Objects[j].name.trim().toLowerCase() === lowercaseObjectName) {
                return TheGame.Objects[j];
            }
        }
    },
    character: function(characterName) {
        if (characterName == null) {
            return null;
        }

        var lowercaseCharacterName = characterName.trim().toLowerCase();
        if(TheGame.Characters.NameMap !== undefined) {
            return TheGame.Characters.NameMap[lowercaseCharacterName];
        }
        console.debug("No NameMap for characters", characterName);
        for (var i = 0; i < TheGame.Characters.length; i++) {
            if (TheGame.Characters[i].Charname.trim().toLowerCase() == lowercaseCharacterName) {
                return TheGame.Characters[i];
            }
        }
    },
    room: function(roomName) {
        if (roomName == null) {
            return null;
        }

        roomName = roomName.trim();
        if(TheGame.Rooms.UidMap !== undefined) {
            const room = TheGame.Rooms.UidMap[roomName];
            if(room !== undefined) return room;
        } else {
            console.debug("No UidMap for rooms", roomName);
            for (var i = 0; i < TheGame.Rooms.length; i++) {
                if (TheGame.Rooms[i].UniqueID == roomName) {
                    return TheGame.Rooms[i];
                }
            }
        }

        var containsDash = roomName.indexOf('-') != -1;
        var lowercaseRoomName = roomName.toLowerCase();
        if(TheGame.Rooms.NameMap !== undefined) {
            return TheGame.Rooms.NameMap[lowercaseRoomName];
        }
        console.debug("No NameMap for rooms", roomName);
        //check by name if we get here
        for (var j = 0; j < TheGame.Rooms.length; j++) {
            var room = TheGame.Rooms[j];
            if (room.Name.trim().toLowerCase() == lowercaseRoomName) {
                return TheGame.Rooms[j];
            }

            // Though it usually produces a UniqueID, sometimes
            // when you manually edit a field in the Rags designer
            // (instead of selecting from a dropdown) the value
            // for a room (in e.x. CT_MOVEPLAYER) will be the
            // room name or `%{name}-%{sdesc}`. So we need to check for that.
            if (containsDash && room.SDesc) {
                var joinedName = [room.Name, room.SDesc].join('-');
                if (joinedName.trim().toLowerCase() == lowercaseRoomName) {
                    return room;
                }
            }
        }
        return null;
    },
    customProp: function (obj, propertyName) {
        if(obj.CustomProperties.NameMap !== undefined) {
            return obj.CustomProperties.NameMap[propertyName];
        }
        console.debug("No NameMap for custom properties", obj, propertyName);
        for (var i = 0; i < obj.CustomProperties.length; i++) {
            var curprop = obj.CustomProperties[i];
            if (curprop.Name == propertyName) {
                return curprop;
            }
        }
    },
    objectGroup: function(groupName) {
        const group = TheGame.Objects.GroupMap[groupName];
        return group === undefined ? [] : group;
    },
    imageGroup: function(groupName) {
        const group = TheGame.Images.GroupMap[groupName];
        return group === undefined ? [] : group;
    },
    /** Add NameMap, UidMap and GroupMap to game arrays to speed up the searches. */
    addMaps: function(gameData) {
        function buildMap(list, keyFunc, map) {
            if(map === undefined) map = {};

            list.forEach((item) => {
                const key = keyFunc(item);
                if(key === undefined) return;
                if(key in map) {
                    console.warn(key + " found multiple times", item, list);
                } else {
                    map[key] = item;
                }
            });

            return map;
        }

        function buildNameMap(list, propName, map) {
            return buildMap(list, (item) => {
                if(propName in item /*&& item[propName]*/) {
                    return item[propName].trim().toLowerCase();
                }
                return undefined;
            }, map);
        }

        function buildUidMap(list, propName, map) {
            return buildMap(list, (item) => {
                return item[propName];
            }, map);
        }

        function buildGroupMap(list, propName) {
            const map = {};

            list.forEach((item) => {
                const name = item[propName];
                if(name === undefined || name === '') return;

                const list = map[name];
                if(list === undefined) {
                    map[name] = [item];
                } else {
                    list.push(item);
                }
            });

            return map;
        }

        // NameMap: Characters, Characters[].Actions, Characters[].CustomProperties,
        //          Objects, Objects[].Actions, Objects[].CustomProperties,
        //          Player.Actions, Player.CustomProperties,
        //          Rooms, Rooms[].Actions, Rooms[].CustomProperties,
        //          Timers, Timers[].Actions, Timers[].CustomProperties,
        //          Variables
        const nameMapTargets = [
            // [list, propName]
            [gameData.Characters, 'Charname'],
            [gameData.Objects, 'name'],
            [gameData.Rooms, 'Name'],
            [gameData.Timers, 'Name'],
            [gameData.Variables, 'varname'],
            [[gameData.Player], 'Name']
        ];

        nameMapTargets.forEach((target) => {
            const list = target[0], propName = target[1];
            list.NameMap = buildNameMap(list, propName);

            // Build NameMap for Actions and CustomProperties if present
            list.forEach((item) => {
                if('Actions' in item) {
                    item.Actions.NameMap = buildNameMap(item.Actions, 'name');
                }
                if('CustomProperties' in item) {
                    item.CustomProperties.NameMap = buildMap(item.CustomProperties, (prop) => {
                        return prop.Name;
                    });
                }
            });
        });

        // Though it usually produces a UniqueID, sometimes
        // when you manually edit a field in the Rags designer
        // (instead of selecting from a dropdown) the value
        // for a room (in e.x. CT_MOVEPLAYER) will be the
        // room name or `%{name}-%{sdesc}`. So we need to check for that.
        buildMap(gameData.Rooms, (room) => {
            return [room.Name, room.SDesc].join('-').trim().toLowerCase();
        }, gameData.Rooms.NameMap);

        // UidMap: Objects, Rooms
        gameData.Objects.UidMap = buildUidMap(gameData.Objects, 'UniqueIdentifier');
        gameData.Rooms.UidMap = buildUidMap(gameData.Rooms, 'UniqueID');

        // GroupMap: Objects, Images
        gameData.Objects.GroupMap = buildGroupMap(gameData.Objects, 'GroupName');
        gameData.Images.GroupMap = buildGroupMap(gameData.Images, 'GroupName');
    }
};
