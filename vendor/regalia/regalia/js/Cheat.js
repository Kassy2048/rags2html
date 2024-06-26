'use strict';

var cheatFreezes = {
    variables: {},
    playerProperties: {}
};

function isFrozenVariable(variable) {
    return !!cheatFreezes.variables[variable.varname];
}

function isFrozenPlayerProperty(property) {
    return !!cheatFreezes.playerProperties[property.Name];
}

$(document).ready(function () {
    $("#cheat_button").click(function (e) {
        $('.cheat-menu').removeClass('hidden');
        $('.cheat-menu').off();
        let hideMenu = false;
        $('.cheat-menu').on('mousedown', function (e) {
            // Hide dialog if click start is outside of the dialog
            if (!$.contains($('.cheat-menu-content')[0], e.target)) {
                hideMenu = true;
            }
        });
        $('.cheat-menu').on('mouseup', function (e) {
            if (hideMenu) {
                $('.cheat-menu').addClass('hidden');
            }
        });

        ReactDOM.render(React.createElement(CheatMenuContent, null), $('.cheat-menu')[0]);
    });

    var originalSetVariable = SetVariable;
    SetVariable = function SetVariable(tempvar, bArraySet, bJavascript, varindex, varindex1a, replacedstring, cmdtxt, part3) {
        if (isFrozenVariable(tempvar)) {
            return;
        }
        return originalSetVariable.apply(this, arguments);
    };

    var originalSetCustomProperty = SetCustomProperty;
    SetCustomProperty = function SetCustomProperty(curprop, part3, replacedstring) {
        if (isFrozenPlayerProperty(curprop)) {
            return;
        }
        return originalSetCustomProperty.apply(this, arguments);
    };
});
