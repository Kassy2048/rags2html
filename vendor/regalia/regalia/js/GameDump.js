function DumpGame() {
    const IDENT_SEP = '  ';
    function ident_str(level) {
        return IDENT_SEP.repeat(level);
    }

    function roomName(id) {
        if(id == CurrentRoomGuid) return '<<CurrentRoom>>';
        let room = Finder.room(id);
        if(!!!room) return '<<???>>';
        return room.Name;
    }

    function objectName(id) {
        if(id == SelfObjectGuid) return '<<CurrentObject>>';
        let obj = Finder.object(id);
        if(!!!obj) return '<<???>>';
        return obj.name;
    }

    function buildCode(commands, indent, condPassed) {
        // condPassed: true, false or undefined
        let result = '';
        let cmdIndex = -1;
        let afterCondition = false;

        commands.forEach((cmd) => {
            ++cmdIndex;
            if('cmdtype' in cmd) {
                if(afterCondition) result += '\n';
                afterCondition = false;

                // Command
                let comments = [];
                if(cmd.CommandName.length > 0) {
                    comments.push(cmd.CommandName);
                }

                // TODO Limit the arguments shown based on command type?
                switch(cmd.cmdtype) {
                    case 'CT_VARIABLE_SET_RANDOMLY': {
                        const tempvar = Finder.variable(cmd.CommandPart2);
                        const randMin = parseInt(PerformTextReplacements(tempvar.dMin));
                        const randMax = parseInt(PerformTextReplacements(tempvar.dMax));
                        comments.push('range=[' + randMin + '; ' + randMax + ']');
                        break;
                    }

                    case 'CT_MOVEITEMTOROOM': {  // part2=Item, part3=Room
                        comments.push('item=' + JSON.stringify(objectName(cmd.CommandPart2)));
                        comments.push('room=' + JSON.stringify(roomName(cmd.CommandPart3)));
                        break;
                    }

                    case 'CT_MOVEITEMTOOBJ': {  // part2=Item, part3=Object
                        comments.push('item=' + JSON.stringify(objectName(cmd.CommandPart2)));
                        comments.push('object=' + JSON.stringify(objectName(cmd.CommandPart3)));
                        break;
                    }

                    case 'CT_MOVEITEMTOCHAR': {  // part2=Item, part3=Character
                        comments.push('item=' + JSON.stringify(objectName(cmd.CommandPart2)));
                        break;
                    }

                    case 'CT_MOVEITEMTOCHAR': {  // part2=Item, part3=Character
                        comments.push('item=' + JSON.stringify(objectName(cmd.CommandPart2)));
                        break;
                    }

                    case 'CT_MOVECHAR': {  // part2=Character, part3=Room
                        comments.push('room=' + JSON.stringify(roomName(cmd.CommandPart3)));
                        break;
                    }

                    case 'CT_SETOBJECTACTION': {  // part2=Object, part3=Action
                        comments.push('object=' + JSON.stringify(objectName(cmd.CommandPart2)));
                        break;
                    }

                    case 'CT_SETROOMACTION': {  // part2=Room, part3=Action
                        comments.push('room=' + JSON.stringify(roomName(cmd.CommandPart2)));
                        break;
                    }

                    default:
                        break;
                }

                if(comments.length > 0) {
                    result += ident_str(indent) + '// ' + comments.join(', ') + '\n';
                }

                result += ident_str(indent) + cmd.cmdtype + '('
                        + JSON.stringify(cmd.CommandPart2) + ', '
                        + JSON.stringify(cmd.CommandPart3) + ', '
                        + JSON.stringify(cmd.CommandPart4) + ', '
                        + JSON.stringify(cmd.CommandText)
                        + (cmd.CustomChoices.length > 0 ? (', ' + JSON.stringify(cmd.CustomChoices)) : '')
                        + ');\n';
            } else {
                // Condition
                const negate = cmd.PassCommands.length == 0 && cmd.FailCommands.length > 0;
                afterCondition = true;

                if(cmdIndex > 0) result += '\n';

                result += ident_str(indent) + '// '+ cmd.conditionname + '\n';
                result += ident_str(indent) + 'if' + (negate ? '(!(' : '(');

                cmd.Checks.forEach((check) => {
                    if(check.CkType == 'And') result += '\n' + ident_str(indent + 2) + '&& ';
                    else if(check.CkType == 'And') result += '\n' + ident_str(indent + 2) + '|| ';
                    // TODO Replace with JS expression when possible
                    result += check.CondType + '('
                        + JSON.stringify(check.ConditionStep2) + ', '
                        + JSON.stringify(check.ConditionStep3) + ', '
                        + JSON.stringify(check.ConditionStep4)
                        + ')';
                });

                result += (negate ? '))' : ')') + ' {\n';

                if(negate) {
                    if(condPassed === false) {
                        result += ident_str(indent + 1) + 'condPassed = false;\n';
                    }
                    result += buildCode(cmd.FailCommands, indent + 1);
                    result += ident_str(indent) + '}\n\n';
                } else {
                    if(condPassed === true) {
                        result += ident_str(indent + 1) + 'condPassed = true;\n';
                    }
                    result += buildCode(cmd.PassCommands, indent + 1);

                    if(cmd.FailCommands.length > 0) {
                        // Replace 'else' with 'else if' when possible
                        if(cmd.FailCommands.length == 1 && !('cmdtype' in cmd.FailCommands[0])
                                && condPassed !== false) {
                            let failCode = buildCode(cmd.FailCommands, indent);

                            // First line is condition name
                            const eol = failCode.indexOf('\n') + 1;
                            result += '\n';
                            result += failCode.slice(0, eol);

                            result += ident_str(indent) + '} else ';
                            result += failCode.slice(eol + ident_str(indent).length);
                        } else {
                            if(condPassed === false) {
                                result += ident_str(indent + 1) + 'condPassed = false;\n';
                            }
                            result += ident_str(indent) + '} else {\n';
                            result += buildCode(cmd.FailCommands, indent + 1);
                            result += ident_str(indent) + '}\n';
                        }
                    } else {
                        result += ident_str(indent) + '}\n';
                    }
                }
            }
        });
        return result;
    }

    function buildActionCode(action, indent) {
        if(action.Conditions.length == 0) {
            // Only care of PassCommands
            return buildCode(action.PassCommands, indent);
        }

        const withCondPassed = action.PassCommands.length != 0
                || action.FailCommands.length != 0;
        let result = '';
        let condPassed;

        // result += ident_str(indent) + '/* Conditions */\n';

        if(!withCondPassed) {
            condPassed = undefined;
        } else if(action.bConditionFailOnFirst) {
            // Execute FailCommands if at least one of the conditions fails
            result += ident_str(indent) + 'let condPassed = true;\n\n';
            condPassed = false;
        } else {
            // Execute PassCommands if at least one of the conditions succeeds
            result += ident_str(indent) + 'let condPassed = false;\n\n';
            condPassed = true;
        }

        result += buildCode(action.Conditions, indent, condPassed);

        if(withCondPassed) {
            // result += ident_str(indent) + '/* Commands */\n';

            if(action.PassCommands.length == 0) {
                result += '\n';
                result += ident_str(indent) + 'if(!condPassed) {\n';
                result += buildCode(action.FailCommands, indent + 1);
                result += ident_str(indent) + '}\n';
            } else if(action.FailCommands.length == 0) {
                result += '\n';
                result += ident_str(indent) + 'if(condPassed) {\n';
                result += buildCode(action.PassCommands, indent + 1);
                result += ident_str(indent) + '}\n';
            } else {
                result += '\n';
                result += ident_str(indent) + 'if(condPassed) {\n';
                result += buildCode(action.PassCommands, indent + 1);
                result += ident_str(indent) + '} else {\n';
                result += buildCode(action.FailCommands, indent + 1);
                result += ident_str(indent) + '}\n';
            }
        }

        return result;
    }

    let result = '';

    ['Player', 'Characters', 'Rooms', 'Objects', 'Timers'].forEach((name) => {
        const is_player = name == 'Player';
        let nodes;
        if(is_player) {
            result += name + ' = {\n';
            nodes = [TheGame.Player];
        } else {
            result += name + ' = [\n';
            nodes = TheGame[name];
        }

        nodes.forEach((c) => {
            let indent = 1;
            if(!is_player) result += ident_str(indent++) + '{\n';

            for(let k in c) {
                if(k == 'Actions') continue;

                let line = ident_str(indent) + k + ': ' + JSON.stringify(c[k]) + ',';

                // Convert locations to room/object names
                if(k == 'CurrentRoom') {
                    line += '  // ' + JSON.stringify(roomName(c[k]));
                } else if(k == 'locationname') {
                    switch(c.locationtype) {
                        case 'LT_ROOM':
                            line += '  // ' + JSON.stringify(roomName(c[k]));
                            break;
                        case 'LT_IN_OBJECT':
                            line += '  // ' + JSON.stringify(objectName(c[k]));
                            break;

                        //case 'LT_CHARACTER':
                        //case 'LT_NULL':
                        //case 'LT_PLAYER':
                        //case 'LT_PORTAL':
                        default:
                            break
                    }
                }

                result += line + '\n';
            }

            result += ident_str(indent++) + 'Actions: [\n';

            c.Actions.forEach((action) => {
                result += ident_str(indent++) + '{\n';

                for(let k in action) {
                    if(k == 'FailCommands' || k == 'PassCommands' || k == 'Conditions') continue;
                    result += ident_str(indent) + k + ': ' + JSON.stringify(action[k]) + ',\n';
                }

                result += ident_str(indent++) + 'run: function() {\n';

                result += buildActionCode(action, indent);

                result += ident_str(--indent) + '},\n';
                result += ident_str(--indent) + '},\n';
            });

            result += ident_str(--indent) + '],\n';
            if(!is_player) result += ident_str(--indent) + '},\n';
        });

        if(is_player) result += '};\n\n';
        else result += '];\n\n';
    });

    return result;
}

document.addEventListener('DOMContentLoaded', () => {
    const savegames_header = document.querySelector('div.savegames-header');

    const dlFile = document.createElement('a');
    dlFile.style.display = 'none';

    const dumpButton = document.createElement('button');
    dumpButton.className = 'btn';
    dumpButton.textContent = 'Dump Game';

    dumpButton.addEventListener('click', (e) => {
        window.URL.revokeObjectURL(dlFile.href);

        const gameData = DumpGame();
        const blob = new Blob([gameData], {type: "text/javascript"});

        dlFile.download = TheGame.Title + ' - ' + TheGame.GameVersion + '.js';
        dlFile.href = window.URL.createObjectURL(blob);
        dlFile.click();
    });

    savegames_header.appendChild(dlFile);
    savegames_header.appendChild(dumpButton);
});