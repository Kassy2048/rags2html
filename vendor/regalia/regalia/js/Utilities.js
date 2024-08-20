var Interactables = {
    inventoryObjects: function () {
        return TheGame.Objects.filter(function (obj) {
            return obj.locationtype == "LT_PLAYER";
        });
    },
    visibleInventoryObjects: function () {
        return this.inventoryObjects().filter(function (obj) {
            return obj.bVisible;
        });
    },
    roomObjects: function () {
        return TheGame.Objects.filter(function (obj) {
            return obj.locationtype == "LT_ROOM" && obj.locationname == TheGame.Player.CurrentRoom;
        });
    },
    visibleRoomObjects: function () {
        return this.roomObjects().filter(function (obj) {
            return obj.bVisible;
        });
    },
    roomAndInventoryObjects: function () {
        return TheGame.Objects.filter(function (obj) {
            return (obj.locationtype == "LT_PLAYER") || (obj.locationtype == "LT_ROOM" && obj.locationname == TheGame.Player.CurrentRoom);
        });
    },
    characters: function () {
        return TheGame.Characters.filter(function (obj) {
            return obj.CurrentRoom == TheGame.Player.CurrentRoom;
        });
    }
};

function escapeQuotedTags(str) {
    var insideQuote = false;
    var result = [];
    var quoteContent = [];
    for (var i = 0; i < str.length; i++) {
        var thisChr = str[i];
        var prevChr = str[i-1];
        if (insideQuote) {
            quoteContent.push(thisChr);
            if (thisChr === "\n") {
                quoteContent[quoteContent.length - 1] = "&lt;br&gt;"
            } else if (thisChr === '"' && prevChr != "\\") {
                result = result.concat(
                    quoteContent
                        .join('')
                        .replace(new RegExp("<\s*\/br\s*>", "g"), "&lt;br&gt;")
                        .replace(new RegExp("<\s*br\s*>", "g"), "&lt;br&gt;")
                        .split('')
                );
                insideQuote = false;
                quoteContent = [];
            }
        } else if (thisChr === '"' && prevChr != "\\") {
            insideQuote = true;
            quoteContent = [thisChr];
        } else {
            result.push(thisChr);
        }
    }
    return result.join('');
}

function evalJankyJavascript(str) {
    // Need to remove newlines in string literals like 'my_str= "foo\nbar"'
    // but <br> tags as exported from RAGS should be treated as real newlines in the source,
    // so statements like "Foo()<br>Bar()" execute correctly.

    var escapedStr = escapeQuotedTags(str)
        .replace(new RegExp("</br>", "g"), "")
        .replace(new RegExp("\n", "g"), "")
        .replace(new RegExp("<br>", "g"), "\n")
        .replace(new RegExp("&lt;br&gt;", "g"), "<br>");

    // If the last statement of the last line ends in 'var foo = something', get rid of the 'var' assignment
    // In the RAGS desktop client, 'var foo = something' seems to return the value of 'something', but
    // in the browser it returns nil. The assignment is inconsequential so let's delete it!
    var lines = escapedStr.split("\n");
    var last_line_statements = lines[lines.length - 1].split(/;(?=.)/);
    last_line_statements[last_line_statements.length - 1] = last_line_statements[last_line_statements.length - 1].replace(/^var\s*[^\s=]+\s*=\s*/, '');
    lines[lines.length - 1] = last_line_statements.join(';');
    escapedStr = lines.join("\n");

    return eval(escapedStr);
}

function SetBorders() {
    if (GetActionCount(Finder.room(TheGame.Player.CurrentRoom).Actions) > 0) {
        //set green border on room thumb
        $("#RoomThumbImg").addClass('has-actions');
    } else {
        $("#RoomThumbImg").removeClass('has-actions');
    }
    if (GetActionCount(TheGame.Player.Actions) > 0) {
        $("#PlayerImg").addClass("has-actions");
    } else {
        $("#PlayerImg").removeClass("has-actions");
    }
}

function GetActionCount(Actions) {
    var count = 0;
    for (var i = 0; i < Actions.length; i++) {
        if (actionShouldBeVisible(Actions[i])) {
            count++;
        }
    }
    return count;
}

var imagePaths = {};
function imagePath(imageName) {
    if (imagePaths[imageName]) {
        return imagePaths[imageName];
    }

    var gameImage = GetGameImage(imageName);
    if (!gameImage) {
        console.log("Unable to find any image named '" + imageName + "'");
        return '';
    }
    imagePaths[imageName] = "images/" + gameImage.TheName.replace(/'/g, '\\\'');
    return imagePaths[imageName];
}

function imageUrl(imageName) {
    return "url('" + imagePath(imageName) + "')";
}

function SetRoomThumb(ImageName) {
    if (ImageName == null || ImageName == "None")
        return;

    $("#RoomImageLayers").empty();

    $("#RoomThumbImg").css("background-image", imageUrl(ImageName));

    var checkimg = GetGameImage(ImageName);
    if (checkimg != null) {
        //layers?
        if (checkimg.LayeredImages[0] != "") {
            var thelayers = checkimg.LayeredImages[0].split(",");
            for (var i = 0; i < thelayers.length; i++) {
                var img = $('<div class="RoomLayeredImage">');
                img.css('background-image', imageUrl(thelayers[i]));
                img.click(function(clickEvent) {
                    Globals.theObj = Finder.room(TheGame.Player.CurrentRoom);
                    GameUI.displayActions(Globals.theObj, clickEvent);
                });
                img.appendTo('#RoomImageLayers');
            }
        }
    }
}

var mainImageExtraLayers = [];
function showImage(ImageName) {
    if (ImageName == null || ImageName == "None")
        return;
    Globals.currentImage = ImageName;
    mainImageExtraLayers = [];
    renderMainImageAndLayers();
}

function renderMainImageAndLayers() {
    $("#MainImageLayers").empty();

    var layers = [];
    var checkimg = GetGameImage(Globals.currentImage);
    if (checkimg != null) {
        if (checkimg.LayeredImages[0] != "") {
            layers = layers.concat(checkimg.LayeredImages[0].split(","));
        }
    }
    layers = layers.concat(mainImageExtraLayers);

    ImageRecorder.sawImage(Globals.currentImage);
    var fileParts = Globals.currentImage.split('.');
    var fileExtension = fileParts[fileParts.length - 1].toLowerCase();
    if (fileExtension === 'mp4' || fileExtension === 'webm') {
        var $videoTag = $('<video autoplay controls width="100%"><source src="' + imagePath(Globals.currentImage) + '" type="video/' + fileExtension + '">Sorry, your browser doesn\'t support this video.</video>');

        $("#MainVideo").empty();
        $("#MainVideo").append($videoTag);
        $("#MainImg").css("background-image", "");
    } else {
        $("#MainVideo").empty();
        $("#MainImg").css("background-image", imageUrl(Globals.currentImage));
    }

    for (var i = 0; i < layers.length; i++) {
        ImageRecorder.sawImage(layers[i]);
        var img = $('<div class="MainLayeredImage"></div>');
        img.css('background-image', imageUrl(layers[i]));
        img.appendTo('#MainImageLayers');
    }
}

function SetPortrait(ImageName) {
    if (ImageName == null || ImageName == "")
        return;
    $("#PortraitImageLayers").empty();

    $("#PlayerImg").css("background-image", imageUrl(ImageName));

    var checkimg = GetGameImage(ImageName);
    if (checkimg != null) {
        //layers?
        if (checkimg.LayeredImages[0] != "") {
            var layers = checkimg.LayeredImages[0].split(",");
            for (var i = 0; i < layers.length; i++) {
                var img = $('<div class="PortraitLayeredImage">');
                img.css('background-image', imageUrl(layers[i]));
                img.click(function(clickEvent) {
                    Globals.theObj = TheGame.Player;
                    GameUI.displayActions(TheGame.Player, clickEvent);
                });
                img.appendTo('#PortraitImageLayers');
            }
        }
    }
}

function SetupStatusBars() {
    var visibleItemTexts = TheGame.StatusBarItems.filter(function (item) {
        return item.bVisible;
    }).map(function (item) {
        return item.Text;
    });
    var statbar = PerformTextReplacements(visibleItemTexts.join(' | '), null);
    $("#statusbartext").empty().append(statbar);
}

function objectContainsObject(container, object) {
    return (object.locationtype === "LT_IN_OBJECT") && (object.locationname === container.UniqueIdentifier) && (object.bVisible);
}

function characterHasObject(character, object) {
    return (object.locationtype === "LT_CHARACTER") && (object.locationname === character.Charname) && (object.bVisible);
}

function nameForAction(action) {
    if (action.overridename) {
        return PerformTextReplacements(action.overridename);
    } else {
        return action.name;
    }
}

function actionShouldBeVisible(action) {
    return action.name.substring(0, 2) !== "<<" && action.bActive && action.actionparent === "None";
}

function isLoopCheck(check) {
    var loopCondTypes = [
        "CT_Loop_While",
        "CT_Loop_Rooms",
        "CT_Loop_Characters",
        "CT_Loop_Items",
        "CT_Loop_Exits",
        "CT_Loop_Item_Char_Inventory",
        "CT_Loop_Item_Container",
        "CT_Loop_Item_Inventory",
        "CT_Loop_Item_Room",
        "CT_Loop_Item_Group"
    ];
    return loopCondTypes.indexOf(check.CondType) > -1;
}

function runNextAfterPause(runNextPhase) {
    if (!GameController.shouldRunCommands()) {
        CommandLists.addToFront(runNextPhase);
    } else {
        runNextPhase();
    }
}

function runAfterPause(runNextPhase) {
    if (!GameController.shouldRunCommands()) {
        CommandLists.addToEnd(runNextPhase);
    } else {
        runNextPhase();
    }
}

function ChangeRoom(currentRoom, bRunTimerEvents, bRunEvents) {
    var commandList = CommandLists.startNestedCommandList();
    var desiredRoomId = currentRoom.UniqueID;
    if (currentRoom == null)
        return;
    $("#RoomTitle").html(roomDisplayName(currentRoom));
    SetRoomThumb(currentRoom.RoomPic);
    showImage(currentRoom.RoomPic);
    TheGame.Player.CurrentRoom = currentRoom.UniqueID;
    if (Globals.movingDirection) {
        $("#MainText").append('</br><b>' + Globals.movingDirection + "</b>");
    }
    if (bRunEvents && !currentRoom.bEnterFirstTime) {
        currentRoom.bEnterFirstTime = true;
        GameActions.runEvents("<<On Player Enter First Time>>", phase2);
    } else {
        phase2();
    }

    function phase2 () {
        runAfterPause(function () {
            // Handle situations where one of the "Enter First Time" events triggers a new ChangeRoom
            if (TheGame.Player.CurrentRoom !== desiredRoomId) {
                return;
            }
            if (bRunEvents) {
                GameActions.runEvents("<<On Player Enter>>", phase3);
            } else {
                phase3();
            }

            function phase3 () {
                runAfterPause(function () {
                    CommandLists.finishNestedCommandList(commandList);

                    // Handle situations where one of the "Enter" events triggers a new ChangeRoom
                    if (TheGame.Player.CurrentRoom !== desiredRoomId) {
                        return;
                    }
                    $("#MainText").animate({
                        scrollTop: $("#MainText")[0].scrollHeight
                    });
                    AddTextToRTF(currentRoom.Description, "Black", "Regular");
                    $("#MainText").animate({
                        scrollTop: $("#MainText")[0].scrollHeight
                    }, 0);
                    ActionRecorder.roomEntered(roomDisplayName(currentRoom));
                    if (bRunTimerEvents)
                        GameTimers.runTimerEvents();
                    GameUI.refreshPanelItems();
                    if ($("#RoomThumb").css("visibility") != "hidden")
                        SetExits();
                    SetBorders();
                });
            }
        });
    }
}

function RoomChange(bRunTimerEvents, bRunEvents) {
    var currentroom = Finder.room(TheGame.Player.CurrentRoom);
    ChangeRoom(currentroom, bRunTimerEvents, bRunEvents);
}

function SetExits() {
    var currentroom = Finder.room(TheGame.Player.CurrentRoom);
    $(".compass-direction").removeClass("active");
    if (currentroom != null) {
        for (var i = 0; i < currentroom.Exits.length; i++) {
            var direction = currentroom.Exits[i].Direction;
            if (currentroom.Exits[i].DestinationRoom != "" && currentroom.Exits[i].bActive) {
                var destRoom = Finder.room(GetDestinationRoomName(direction));
                $(".compass-direction[data-direction=" + direction + "]").addClass("active")
                        .text(roomDisplayName(destRoom));
            } else {
                $(".compass-direction[data-direction=" + direction + "]").text('');
            }
        }
    }
}

function RefreshPictureBoxes() {
    showImage(Globals.currentImage);
    SetPortrait(TheGame.Player.PlayerPortrait);

    SetRoomThumb(Finder.room(TheGame.Player.CurrentRoom).RoomPic);
}

function movePlayerToRoom(roomName) {
    Globals.movingDirection = "";
    TheGame.Player.CurrentRoom = roomName;
    if (TheGame.Player.CurrentRoom) {
        RoomChange(false, true);
    }
}

function AddTextToRTF(text, clr, fontst) {
    var origtext = "";
    while (origtext != text) {
        origtext = text;
        text = PerformTextReplacements(text, null);
    }

    if (TheGame.RagsVersion < 3.0) { // RAGS 3.0 uses HTML tags
        text = escapeHtmlSpecialCharacters(text);

        // unescape the <br> or <br/> tags that just got escaped
        text = text.replace(/&lt;\s*[/]?\s*br\s*[/]?\s*&gt;/g, '<br>')
    } else {
        // TODO Remove leading "<br/>"?
    }

    var replacedtext = text;
    if (fontst == "Regular" && clr == "Black") {
        // [c Green]green text[/c]
        replacedtext = replacedtext.replace(/\[c\s*([^\]]+)]/gi, function (match, colortype) {
            var colorinserter = "<span style='color:";
            if (colortype.indexOf(",") > -1) {
                colorinserter += "rgb(" + colortype + ");'>";
            } else {
                colorinserter += colortype + ";'>";
            }
            return colorinserter;
        });

        // [f Arial,16]special font[/f]
        replacedtext = replacedtext.replace(/\[f\s*([^\]]+)]/gi, function (match, fonttype) {
            var fontdata = fonttype.split(",");
            return "<span style='font-family:" + fontdata[0] + ";font-size:" +
                fontdata[1] + "px;'>";
        });

        // [b]bold text[/b]
        replacedtext = replacedtext.replace(/\[b]/gi, function (match) {
            return "<span style='font-weight:bold;'>";
        });

        // [i]italic text[/i]
        replacedtext = replacedtext.replace(/\[i]/gi, function (match) {
            return "<span style='font-style:italic;'>";
        });

        // [u]underlined text[/u]
        replacedtext = replacedtext.replace(/\[u]/gi, function (match) {
            return "<span style='text-decoration:underline;'>";
        });

        // closing tags ([/u], [/b]...)
        replacedtext = replacedtext.replace(/\[\/[fciub]]/gi, function (match) {
            return "</span>";
        });

        var styleformats = [];
        var tempindex;
        text = MiddlesOnly(replacedtext);
        tempindex = text.indexOf("[middle]", 0);
        while (tempindex >= 0) {
            text = text.slice(0, tempindex) + text.slice(tempindex + 8);
            var endindex = text.indexOf("[/middle]", tempindex);
            if (endindex >= 0) {
                text = text.slice(0, endindex) + text.slice(endindex + 9);
                styleformats.push([
                    text.substring(tempindex, endindex),
                    "<div style=\"text-align:center;\">"
                ]);
            }
            tempindex = text.indexOf("[middle]", 0);
        }
        text = TextOnly(replacedtext);
        for (var i = 0; i < styleformats.length; i++) {
            var startindex = text.indexOf(styleformats[i][0]);
            text = text.slice(0, startindex) + styleformats[i][1] + text.slice(startindex);
            startindex = text.indexOf(styleformats[i][0]);
            text = text.slice(0, startindex + styleformats[i][0].length) + "</div>" + text.slice(startindex + styleformats[i][0].length);
        }

        $("#MainText").append('</br>' + text);
    } else {
        $("#MainText").append('</br>' + text);
    }
}

function escapeHtmlSpecialCharacters(str) {
    var tagsToReplace = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;'
    };
    return str.replace(/[&<>]/g, function(tag) {
        return tagsToReplace[tag] || tag;
    });
};

function nthIndex(str, pat, n){
    var i = -1;
    while(n >= 0 && i++ < str.length){
        i = str.indexOf(pat, i);
        if (i < 0) break;
        n--;
    }
    return i;
}

function GetArrayIndex(varname, n) {
    var retval = -1;
    var index = nthIndex(varname, "(", n);
    if (index > -1) {
        var endindex = varname.indexOf(")", index);
        if (endindex > -1) {
            var indexvalue = varname.substring(index + 1, endindex);
            try {
                retval = indexvalue;
            } catch (err) {
                retval = -1;
            }
        }
    }

    if (retval && retval !== -1) {
        var rangeMatch = retval.match(/(\d+)\.\.(\d+)/);
        if (rangeMatch) {
            return -1;
        }
    }

    return retval;
}

function getObjectClass(obj) {
    if (obj && obj.constructor && obj.constructor.toString) {
        var arr = obj.constructor.toString().match(/function\s*(\w+)/);
        if (arr && arr.length == 2) {
            return arr[1];
        }
    }
    return undefined;
}

function CheckItemInInventory(tempobj) {
    var foundObj = TheGame.Objects.filter(function (obj) {
        return obj.name == tempobj.locationname;
    })[0];

    if (!foundObj) {
        return false;
    }

    if (foundObj.locationtype == "LT_PLAYER") {
        return true;
    } else if (foundObj.locationtype == "LT_IN_OBJECT") {
        return CheckItemInInventory(foundObj);
    } else {
        return false;
    }
}

function GetCustomChoiceAction(type, name, actionname) {
    var tempact = null;
    if (type == "Chr") {
        tempact = Finder.action(Finder.character(name).Actions, actionname);
    } else if (type == "Obj") {
        var tempobj = Finder.object(name);
        if (tempobj != null)
            tempact = Finder.action(tempobj.Actions, actionname);
    } else if (type == "Player") {
        tempact = Finder.action(TheGame.Player.Actions, actionname);
    } else if (type == "Room") {
        var temproom = Finder.room(name);
        if (temproom != null)
            tempact = Finder.action(temproom.Actions, actionname);
    } else if (type == "Timer") {
        var temptimer = Finder.timer(name);
        if (temptimer != null)
            tempact = Finder.action(temptimer.Actions, actionname);
    }
    return tempact;
}

function PauseGame() {
    GameController.pause();
    $("#Continue").css('background-color', "rgb(255, 255, 255)");
    $("#Continue").css('visibility', "visible");
}

function TestCustomProperty(PropVal, step3, step4) {
    var bResult = true;
    var replacedstring = PerformTextReplacements(step4, null);
    var bIntComparison = false;
    var iPropVal = 0.0;
    var iReplacedString = 0.0;
    try {
        iPropVal = parseInt(PropVal);
        iReplacedString = parseInt(replacedstring);
        if (isNaN(iPropVal))
            bIntComparison = false;
        else
            bIntComparison = true;
    } catch (err) {
        bIntComparison = false;
    }
    if (step3 == "Equals") {
        if (bIntComparison) {
            bResult = iReplacedString == iPropVal;
        } else {
            bResult = replacedstring.toLowerCase() == PropVal.toLowerCase();
        }
    } else if (step3 == "Not Equals") {
        if (bIntComparison) {
            bResult = iReplacedString != iPropVal;
        } else {
            bResult = replacedstring.toLowerCase() != PropVal.toLowerCase();
        }
    } else if (step3 == "Contains") {
        bResult = (PropVal.toLowerCase().indexOf(replacedstring.toLowerCase()) >= 0);
    } else if (step3 == "Greater Than") {
        if (bIntComparison) {
            bResult = iPropVal > iReplacedString;
        } else {
            bResult = replacedstring > PropVal;
        }
    } else if (step3 == "Greater Than or Equals") {
        if (bIntComparison) {
            bResult = iPropVal >= iReplacedString;
        } else {
            bResult = replacedstring >= PropVal;
        }
    } else if (step3 == "Less Than") {
        if (bIntComparison) {
            bResult = iPropVal < iReplacedString;
        } else {
            bResult = replacedstring < PropVal;
        }
    } else if (step3 == "Less Than or Equals") {
        if (bIntComparison) {
            bResult = iPropVal <= iReplacedString;
        } else {
            bResult = replacedstring <= PropVal;
        }
    }
    return bResult;
}

function SetArrayData(tempvar, resultval) {
    var bMDA = false;
    var arWidth = 0;
    if (tempvar.VarArray.length > 0) {
        var test = tempvar.VarArray[0];
        if (test.length > 0) {
            bMDA = true;
            arWidth = test.length;
        }
    }
    tempvar.VarArray = resultval;
    var temparray = resultval;
}

function SetVariable(tempvar, bArraySet, bJavascript, varindex, varindex1a, replacedstring, cmdtxt, part3) {
    if (tempvar.vartype == "VT_DATETIMEARRAY" || tempvar.vartype == "VT_DATETIME") {
        var dateMoment = DateTimes.stringDateToMoment(tempvar.dtDateTime);
        if (part3 == "Add Days") {
            dateMoment.add(replacedstring, "day");
        } else if (part3 == "Add Hours") {
            dateMoment.add(replacedstring, "hour");
        } else if (part3 == "Add Minutes") {
            dateMoment.add(replacedstring, "minute");
        } else if (part3 == "Add Seconds") {
            dateMoment.add(replacedstring, "second");
        } else if (part3 == "Subtract Days") {
            dateMoment.subtract(replacedstring, "day");
        } else if (part3 == "Subtract Hours") {
            dateMoment.subtract(replacedstring, "hour");
        } else if (part3 == "Subtract Minutes") {
            dateMoment.subtract(replacedstring, "minute");
        } else if (part3 == "Subtract Seconds") {
            dateMoment.subtract(replacedstring, "second");
        } else if (part3 == "Set Day Of Month To") {
            dateMoment.date(replacedstring);
        } else if (part3 == "Set Hours To") {
            dateMoment.hour(replacedstring);
        } else if (part3 == "Set Minutes To") {
            dateMoment.minute(replacedstring);
        } else if (part3 == "Set Seconds To") {
            dateMoment.second(replacedstring);
        } else if (part3 == "Equals") {
            dateMoment = DateTimes.stringDateToMoment(replacedstring);
        }
        tempvar.dtDateTime = dateMoment.format(DateTimes.defaultDateFormat);
    } else if (tempvar.vartype == "VT_NUMBERARRAY" || tempvar.vartype == "VT_NUMBER") {
        if (part3 == "Equals") {
            if (bArraySet) {
                SetArrayData(tempvar, jsresult);
            } else {
                if (varindex == -1)
                    tempvar.dNumType = parseFloat(replacedstring);
                else {
                    if (varindex1a != -1)
                        tempvar.VarArray[varindex][varindex1a] = replacedstring;
                    else
                        tempvar.VarArray[varindex] = parseFloat(replacedstring);
                }
            }
        } else if (part3 == "Add") {
            if (varindex == -1)
                tempvar.dNumType += parseFloat(replacedstring);
            else {
                if (varindex1a != -1)
                    tempvar.VarArray[varindex][varindex1a] = (parseFloat(tempvar.VarArray[varindex][varindex1a]) +
                        parseFloat(replacedstring)).toString();
                else
                    tempvar.VarArray[varindex] = parseFloat(tempvar.VarArray[varindex]) +
                    parseFloat(replacedstring);
            }
        } else if (part3 == "Subtract") {
            if (varindex == -1)
                tempvar.dNumType -= parseFloat(replacedstring);
            else {
                if (varindex1a != -1)
                    tempvar.VarArray[varindex][varindex1a] = (parseFloat(tempvar.VarArray[varindex][varindex1a]) -
                        parseFloat(replacedstring)).toString();
                else
                    tempvar.VarArray[varindex] = parseFloat(tempvar.VarArray[varindex]) -
                    parseFloat(replacedstring);
            }
        } else if (part3 == "Multiply") {
            if (varindex == -1)
                tempvar.dNumType *= parseFloat(replacedstring);
            else {
                if (varindex1a != -1)
                    tempvar.VarArray[varindex][varindex1a] = (parseFloat(tempvar.VarArray[varindex][varindex1a]) * parseFloat(replacedstring)).toString();
                else
                    tempvar.VarArray[varindex] = parseFloat(tempvar.VarArray[varindex]) * parseFloat(replacedstring);
            }
        } else if (part3 == "Divide") {
            if (varindex == -1)
                tempvar.dNumType /= parseFloat(replacedstring);
            else {
                if (varindex1a != -1)
                    tempvar.VarArray[varindex][varindex1a] = (parseFloat(tempvar.VarArray[varindex][varindex1a]) / parseFloat(replacedstring)).toString();
                else
                    tempvar.VarArray[varindex] = parseFloat(tempvar.VarArray[varindex]) / parseFloat(replacedstring);
            }
        }
        if (tempvar.bEnforceRestrictions) {
            if (varindex == -1) {
                if (tempvar.dNumType < parseFloat(PerformTextReplacements(tempvar.dMin, null)))
                    tempvar.dNumType = parseFloat(PerformTextReplacements(tempvar.dMin, null));
                if (tempvar.dNumType > parseFloat(PerformTextReplacements(tempvar.dMax, null)))
                    tempvar.dNumType = parseFloat(PerformTextReplacements(tempvar.dMax, null));
            } else {
                if (varindex1a != -1) {
                    if (parseFloat(tempvar.VarArray[varindex][varindex1a]) < parseFloat(PerformTextReplacements(tempvar.dMin, null)))
                        tempvar.VarArray[varindex][varindex1a] = PerformTextReplacements(tempvar.dMin, null).toString();
                    if (parseFloat(tempvar.VarArray[varindex][varindex1a]) > parseFloat(PerformTextReplacements(tempvar.dMax, null)))
                        tempvar.VarArray[varindex][varindex1a] = PerformTextReplacements(tempvar.dMax, null).toString();
                } else {
                    if (parseFloat(tempvar.VarArray[varindex]) < parseFloat(PerformTextReplacements(tempvar.dMin, null)))
                        tempvar.VarArray[varindex] = parseFloat(PerformTextReplacements(tempvar.dMin, null));
                    if (parseFloat(tempvar.VarArray[varindex]) > parseFloat(PerformTextReplacements(tempvar.dMax, null)))
                        tempvar.VarArray[varindex] = parseFloat(PerformTextReplacements(tempvar.dMax, null));
                }
            }
        }
    } else if (tempvar.vartype == "VT_STRINGARRAY" || tempvar.vartype == "VT_STRING") {
        if (bJavascript) {
            var jsresult = evalJankyJavascript(cmdtxt);
            if (!bArraySet && jsresult != null)
                cmdtxt = jsresult.toString();
        }
        if (bArraySet) {
            SetArrayData(tempvar, jsresult);
        } else {
            if (varindex == -1)
                tempvar.sString = cmdtxt;
            else
            if (varindex1a != -1)
                tempvar.VarArray[varindex][varindex1a] = cmdtxt;
            else
                tempvar.VarArray[varindex] = cmdtxt;
        }
    }
}

function SetRagsObjectsFromJavascript(resultval) {
    var temparray = resultval;
    if (temparray != null) {
        for (var i = 0; i < temparray.length; i++) {
            var tempobj = temparray[i];
            if (tempobj.length > 0) {
                var objtomodify = "[" + tempobj[0].toString() + "]";
                var newval = tempobj[1].toString();
                if (newval == "")
                    newval = " ";
                PerformTextReplacements(objtomodify, null, newval);
            }
        }
    }
}

function CheckNumericLimits(tempvar, thevalue) {
    //check min/max limits...
    if (tempvar.bEnforceRestrictions) {
        var themin = parseFloat(PerformTextReplacements(tempvar.dMin, null));
        var themax = parseFloat(PerformTextReplacements(tempvar.dMax, null));
        if (parseFloat(thevalue) < themin)
            return themin;
        if (parseFloat(thevalue) > themax)
            return themax;
        return parseFloat(thevalue);

    } else
        return parseFloat(thevalue);
}

function SetCommandInput(tempcommand, value) {
    var part2 = PerformTextReplacements(tempcommand.CommandPart2, null);
    var part3 = PerformTextReplacements(tempcommand.CommandPart3, null);
    var part4 = PerformTextReplacements(tempcommand.CommandPart4, null);
    var cmdtxt = PerformTextReplacements(tempcommand.CommandText, null);
    var tempvar = Finder.variable(part3);
    var varindex = GetArrayIndex(part3, 0);
    var varindex3a = GetArrayIndex(part3, 1);
    if (tempvar != null) {
        switch (tempcommand.cmdtype) {
            case "CT_SETVARIABLE_NUMERIC_BYINPUT":
                {
                    if (varindex == -1) {
                        tempvar.dNumType = CheckNumericLimits(tempvar, value);
                    } else {
                        if (varindex3a != -1) {
                            tempvar.VarArray[varindex][varindex3a] = "";
                            tempvar.VarArray[varindex][varindex3a] = CheckNumericLimits(tempvar, value).toString();
                        } else {
                            tempvar.VarArray[varindex] = "";
                            tempvar.VarArray[varindex] = CheckNumericLimits(tempvar, value).toString();
                        }
                    }
                    break;
                }
            case "CT_SETVARIABLEBYINPUT":
                {
                    var acttype = part2;
                    var tempvar = Finder.variable(part3);
                    var varindex = GetArrayIndex(part3, 0);
                    var varindex3a = GetArrayIndex(part3, 1);
                    var valueToSave;
                    if (value.constructor.name === "ragsobject") {
                        valueToSave = value.name;
                    } else if (acttype === "Character" || acttype === "ObjectOrCharacter") {
                        valueToSave = Finder.character(value).Charname;
                    } else {
                        valueToSave = value;
                    }
                    if (tempvar != null) {
                        if (varindex == -1) {
                            tempvar.sString = valueToSave;
                        } else {
                            if (varindex3a != -1) {
                                tempvar.VarArray[varindex][varindex3a] = "";
                                tempvar.VarArray[varindex][varindex3a] = valueToSave;
                            } else {
                                tempvar.VarArray[varindex] = "";
                                tempvar.VarArray[varindex] = valueToSave;
                            }
                        }
                    }
                }
        }
    }
}

function SetCustomProperty(curprop, part3, replacedstring) {
    var bInteger = true;
    var iReplacedString = parseFloat(replacedstring);
    var iPropVal = parseFloat(curprop.Value);
    if (isNaN(parseFloat(curprop.Value)) && isNaN(parseFloat(replacedstring))) {
        bInteger = false;
    }
    if (part3 == "Equals") {
        curprop.Value = replacedstring;
    } else if (part3 == "Add") {
        if (bInteger) {
            curprop.Value = (iReplacedString + iPropVal).toString();
        }
    } else if (part3 == "Subtract") {
        if (bInteger) {
            curprop.Value = (iPropVal - iReplacedString).toString();
        }
    } else if (part3 == "Multiply") {
        if (bInteger) {
            curprop.Value = (iReplacedString * iPropVal).toString();
        }
    } else if (part3 == "Divide") {
        if (bInteger) {
            curprop.Value = (iPropVal / iReplacedString).toString();
        }
    }
}

function UpdateStatusBars() {
    SetupStatusBars();
}

function GetExit(room, dir) {
    for (var i = 0; i < room.Exits.length; i++) {
        if (room.Exits[i].Direction == dir) {
            return room.Exits[i];
        }
    }
    return null;
}