function DumpGame() {
    const IDENT_SEP = '  ';
    function ident_str(level) {
        return IDENT_SEP.repeat(level);
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
                result += ident_str(indent) + cmd.cmdtype + '('
                        + JSON.stringify(cmd.CommandPart2) + ', '
                        + JSON.stringify(cmd.CommandPart3) + ', '
                        + JSON.stringify(cmd.CommandPart4) + ', '
                        + JSON.stringify(cmd.CommandText)
                        + (cmd.CustomChoices.length > 0 ? (', ' + JSON.stringify(cmd.CustomChoices)) : '')
                        + ');';

                if(cmd.CommandName.length > 0) {
                    result += '  // ' + cmd.CommandName;
                }

                result += '\n';
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
                result += ident_str(indent) + k + ': ' + JSON.stringify(c[k]) + ',\n';
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