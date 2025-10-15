var GameUI = {
    saveDisabled: false,

    setGameTitle: function () {
        var title = GameController.title();
        if (TheGame.GameVersion !== undefined && TheGame.GameVersion.length > 0) {
            version = ' (' + TheGame.GameVersion + ')';
        } else {
            version = '';
        }

        document.title = title + version;
        $('.game-title').text(title);
        $('.game-version').text(version);
    },

    setDefaultCompass: function () {
        $(".compass-rose").css("background-image", 'url("images/300px-Compass_Rose_English_North.png")');
        $(".compass-up-down").css("background-image", 'url("images/300px-Compass_Rose_UD.png")');
    },

    setInputMenuTitle: function (act) {
        $("#InputMenuTitle").text(PerformTextReplacements(act.CustomChoiceTitle, null));
        $("#inputmenu").css("visibility", "visible");
        var cancellable = (act.EnhInputData && act.EnhInputData.bAllowCancel) || act.CustomChoices.length === 0;
        $("#inputmenu").toggleClass('cancellable', cancellable);
    },

    showGameElements: function () {
        $("#RoomThumbImg").css("visibility", "visible");
        $("#PlayerImg").css("visibility", "visible");
        $("#RoomObjectsPanel").css("visibility", "visible");
        $("#VisibleCharactersPanel").css("visibility", "visible");
        $("#InventoryPanel").css("visibility", "visible");
        $(".compass-direction").css("visibility", "visible");
        SetExits();
    },

    hideGameElements: function () {
        $("#PlayerImg").css("visibility", "hidden");
        $("#RoomThumbImg").css("visibility", "hidden");
        $("#RoomObjectsPanel").css("visibility", "hidden");
        $("#VisibleCharactersPanel").css("visibility", "hidden");
        $("#InventoryPanel").css("visibility", "hidden");
        $(".compass-direction").css("visibility", "hidden");
    },

    disableSaveAndLoad: function () {
        this.saveDisabled = true;
        $('#back').prop('disabled', true)
                .prop('title', 'Cannot go back now');
    },

    enableSaveAndLoad: function () {
        this.saveDisabled = false;
        $('#back').prop('disabled', !GameHistory.canGoBack())
            .prop('title', GameHistory.noGoBackReason());
    },

    clearInputChoices: function () {
        $("#inputchoices").empty();
    },

    clearCmdInputChoices: function () {
        $("#cmdinputchoices").empty();
    },

    setCmdInputMenuTitle: function (act, title) {
        $("#cmdInputMenuTitle").text(title);
        $("#cmdinputmenu").css("visibility", "visible");
        $("#cmdinputmenu").toggleClass('cancellable', act.EnhInputData && act.EnhInputData.bAllowCancel);
    },

    addInputChoice: function (act, text, value) {
        var $div = $("<div>", {
            class: "inputchoices",
            text: text
        });

        $div.click(function() {
            Globals.selectedObj = value;
            if (Globals.selectedObj != null) {
                GameController.executeAndRunTimers(function () {
                    CommandLists.setAdditionalData(Globals.selectedObj);
                    GameController.stopAwaitingInput();
                    $("#inputmenu").css("visibility", "hidden");
                    if (getObjectClass(act) == "action" || "actionparent" in act) {
                        ActionRecorder.choseInputAction(text);
                        GameActions.executeAction(act, true);
                        GameCommands.runCommands();
                        GameUI.onInteractionResume();
                    }
                });
            }
        });

        $("#inputchoices").append($div);
    },

    addCmdInputChoice: function (text, value) {
        var $div = $("<div>", {
            class: "inputchoices",
            text: text
        });

        $div.click(function () {
            Globals.selectedObj = value;
            if (Globals.selectedObj != null) {
                GameController.executeAndRunTimers(function () {
                    $("#cmdinputmenu").hide();
                    GameController.stopAwaitingInput();
                    $("#cmdinputmenu").css("visibility", "hidden");
                    ActionRecorder.choseInputAction(text);
                    SetCommandInput(Globals.variableGettingSet, Globals.selectedObj);
                    GameCommands.runCommands();
                    GameUI.onInteractionResume();
                });
            }
        });

        $("#cmdinputchoices").append($div);
        $("#cmdinputmenu").show();
    },

    addCharacterOptions: function (act) {
        Interactables.characters().forEach(function (character) {
            if (act) {
                GameUI.addInputChoice(act, CharToString(character), character.Charname);
            } else {
                GameUI.addCmdInputChoice(CharToString(character), character.Charname);
            }
        });
    },

    addObjectOptions: function (act) {
        Interactables.roomAndInventoryObjects().forEach(function (obj) {
            if (act) {
                GameUI.addInputChoice(act, objecttostring(obj), obj);
            } else {
                GameUI.addCmdInputChoice(objecttostring(obj), obj);
            }
        });
    },

    setCmdInputForCustomChoices: function (title, tempcommand) {
        this.clearCmdInputChoices();
        for (var i = 0; i < tempcommand.CustomChoices.length; i++) {
            var text = PerformTextReplacements(tempcommand.CustomChoices[i]);
            this.addCmdInputChoice(text, text);
        }
        this.setCmdInputMenuTitle(tempcommand, title);
    },

    showTextMenuChoice: function (title) {
        $("#textMenuTitle").text(title);
        $("#textchoice").css("visibility", "visible");
        $("#textchoice input").focus();
    },

    addActionChoice: function (obj, action, text) {
        var $div = $("<div>", {
            class: "ActionChoices",
            text: text,
            value: action.name
        });

        $div.click(function (e) {
            var selectionchoice = $(this).val();
            var selectiontext = $(this).text();
            if (selectionchoice != null) {
                GameController.executeAndRunTimers(function () {
                    ActionRecorder.actedOnObject(obj, selectiontext);
                    $("#MainText").append('</br><b>' + selectionchoice + "</b>");
                    $("#MainText").animate({
                        scrollTop: $("#MainText")[0].scrollHeight
                    });
                    $("#selectionmenu").css("visibility", "hidden");
                    ResetLoopObjects();
                    TheGame.TurnCount++;
                    GameActions.processAction(selectionchoice, false, obj);
                    GameUI.onInteractionResume();
                });
            }
        });

        $("#Actionchoices").append($div);
        return $div;
    },

    displayActions: function (obj, clickEvent) {
        var actions = obj.Actions;
        if (GetActionCount(actions) === 0) {
            return;
        }

        $("#Actionchoices").empty();
        Globals.curActions = actions;
        for (var i = 0; i < actions.length; i++) {
            var action = actions[i];
            if (actionShouldBeVisible(action)) {
                this.addActionChoice(obj, action, nameForAction(action));
                this.addChildActions(obj, actions, "--", action.name);
            }
        }

        $("#selectionmenu").click(function (e) {
            e.stopPropagation();
        });

        $('body').off('click.selectionmenu');
        setTimeout(function () {
            $('body').on('click.selectionmenu', function (e) {
                $("#selectionmenu").css("visibility", "hidden");
            });
        });

        var leftPosition = clickEvent.clientX;
        var topPosition = clickEvent.clientY;
        var rightPosition = leftPosition + $("#selectionmenu").width();
        var bottomPosition = topPosition + $("#selectionmenu").height();
        var windowWidth = $(window).width();
        var windowHeight = $(window).height();
        var fudgeFactor = 2;
        if (rightPosition > windowWidth - fudgeFactor) {
            leftPosition -= (rightPosition - windowWidth + fudgeFactor);
        }
        if (bottomPosition > windowHeight - fudgeFactor) {
            topPosition -= (bottomPosition - windowHeight + fudgeFactor);
        }

        $("#selectionmenu").css("top", topPosition + "px");
        $("#selectionmenu").css("left", leftPosition + "px");
        $("#selectionmenu").css("visibility", "visible");
        $("#Actionchoices").focus();
    },

    addChildActions: function (obj, actions, Indent, ActionName) {
        for (var i = 0; i < actions.length; i++) {
            var action = actions[i];
            if (action.name.substring(0, 2) != "<<" && action.bActive && action.actionparent == ActionName) {
                this.addActionChoice(obj, action, Indent + nameForAction(action));
                this.addChildActions(obj, actions, "--" + Indent, action.name);
            }
        }
    },

    addOpenedObjects: function(outerObject, thelistbox, itemclass) {
        TheGame.Objects.forEach(function (innerObject) {
            if (
                (objectContainsObject(outerObject, innerObject)) ||
                ((outerObject.constructor.name === "character") && characterHasObject(outerObject, innerObject))
            ) {
                thelistbox.append(
                    GameUI.panelLink(
                        itemclass,
                        '--' + objecttostring(innerObject),
                        innerObject.UniqueIdentifier,
                        innerObject.Actions,
                        Finder.object
                    )
                );
                
                if (innerObject.bOpenable && innerObject.bOpen) {
                    GameUI.addOpenedObjects(innerObject, thelistbox, itemclass);
                }
            }
        });
    },

    refreshRoomObjects: function () {
        $("#RoomObjects").empty();
        Interactables.visibleRoomObjects().forEach(function (obj) {
            $("#RoomObjects").append(
                GameUI.panelLink(
                    'RoomObjects',
                    objecttostring(obj),
                    obj.UniqueIdentifier,
                    obj.Actions,
                    Finder.object
                )
            );

            if (obj.bContainer) {
                if (!obj.bOpenable || obj.bOpen) {
                    GameUI.addOpenedObjects(obj, $("#RoomObjects"), 'RoomObjects');
                }
            }
        });
        if (TheGame.Player.CurrentRoom != null) {
            var currentroom = Finder.room(TheGame.Player.CurrentRoom);
            if (currentroom != null) {
                for (var j = 0; j < currentroom.Exits.length; j++) {
                    var tempexit = currentroom.Exits[j];
                    if (tempexit.PortalObjectName != "<None>") {
                        var tempobj = Finder.object(tempexit.PortalObjectName);
                        if (tempobj != null) {
                            if (tempobj.bVisible) {
                                $("#RoomObjects").append(
                                    GameUI.panelLink(
                                        'RoomObjects',
                                        objecttostring(tempobj),
                                        tempobj.UniqueIdentifier,
                                        tempobj.Actions,
                                        Finder.object
                                    )
                                );

                                if (tempobj.bContainer) {
                                    if (!tempobj.bOpenable || tempobj.bOpen) {
                                        GameUI.addOpenedObjects(tempobj, $("#RoomObjects"), 'RoomObjects');
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    },

    refreshInventory: function () {
        $("#Inventory").empty();
        Interactables.visibleInventoryObjects().forEach(function (obj) {
            $("#Inventory").append(
                GameUI.panelLink(
                    'RoomObjects',
                    objecttostring(obj),
                    obj.UniqueIdentifier,
                    obj.Actions,
                    Finder.object
                )
            );

            if (obj.bContainer) {
                if (!obj.bOpenable || obj.bOpen) {
                    GameUI.addOpenedObjects(obj, $("#Inventory"), 'RoomObjects');
                }
            }
        });
    },

    refreshCharacters: function () {
        $("#VisibleCharacters").empty();
        Interactables.characters().forEach(function (obj) {
            $("#VisibleCharacters").append(
                GameUI.panelLink(
                    'VisibleCharacters',
                    CharToString(obj),
                    obj.Charname,
                    obj.Actions,
                    Finder.character
                )
            );

            if (obj.bAllowInventoryInteraction) {
                GameUI.addOpenedObjects(obj, $("#VisibleCharacters"), 'VisibleCharacters');
            }
        });
    },

    panelLink: function (itemClass, text, value, actions, objFinderFunction) {
        var $div = $("<div>", {
            class: itemClass,
            text: text,
            value: value
        });
        $div.toggleClass('no-actions', GetActionCount(actions) === 0);

        $div.click(function(clickEvent) {
            // TODO: this is the main place that stashes Globals.selectedObj, try to get rid of it
            Globals.selectedObj = objFinderFunction($(this).val());
            if (Globals.selectedObj != null) {
                Globals.theObj = Globals.selectedObj;
                GameUI.displayActions(Globals.selectedObj, clickEvent);
            }
        });
        return $div;
    },

    refreshPanelItems: function () {
        this.refreshInventory();
        this.refreshRoomObjects();
        this.refreshCharacters();
    },

    displayLiveTimers: function () {
        var activeLiveTimers = GameTimers.activeLiveTimers();
        $('.live-timer-display').toggle(activeLiveTimers.length > 0);
        if (activeLiveTimers.length > 0) {
            var $container = $('.live-timer-display-rows');
            $container.empty();
            activeLiveTimers.forEach(function (timer) {
                var $timerRow = $('<tr>');
                $timerRow.append('<td>' + timer.Name + '</td>');
                $timerRow.append('<td>' + (timer.TimerSeconds - (timer.curtickcount / 1000)) + 's</td>');
                $timerRow.append('<td><b>Click to Skip</b></td>');
                $timerRow.data('timer-name', timer.Name);
                $timerRow.click(function () {
                    var timerName = $(this).data('timer-name');
                    var timer = Finder.timer(timerName);
                    var secondsRemaining = (timer.TimerSeconds - (timer.curtickcount / 1000));
                    for (var i = 0; i < secondsRemaining; i++) {
                        GameTimers.tickLiveTimers(true);
                    }
                    GameUI.refreshPanelItems();
                    GameUI.displayLiveTimers();
                });
                $container.append($timerRow);
            });
        }
    },

    onInteractionResume: function() {
        const MainText = $("#MainText");
        const scrollHeight = MainText[0].scrollHeight;
        if(this.lastScrollHeight != scrollHeight) {
            MainText.append('<hr>');
            if(this.lastScrollHeight !== undefined) {
                MainText.animate({
                    scrollTop: this.lastScrollHeight
                }, 0);
            }
            this.lastScrollHeight = MainText[0].scrollHeight;
        }

        if(GameController.shouldRunCommands()) {
            GameHistory.pushState();
            $('#back').prop('disabled', !GameHistory.canGoBack())
                    .prop('title', GameHistory.noGoBackReason());
        }
    },

    showMessage: function(text, params) {
        if(params === undefined) {
            params = {
                //type: string,    // message type: error, warning, success
                //timeout: float,  // message type: seconds before hiding it
                //html: boolean,   // message text is HTML if set
            };
        }

        const $message = $('<div class="message"><div class="message-close"></div></div>');

        switch(params.type) {
            case 'error': $message.addClass('error'); break;
            case 'warning': $message.addClass('warning'); break;
            case 'success': $message.addClass('success'); break;
            case undefined: break;
            default: console.warn(`Message type ${params.type} is not supported`);
        }

        const $text = $('<div class="message-text"></div>');
        if(params.html) $text.html(text);
        else $text.text(text);
        console.log(text);

        $message.prepend($text);

        $message.on('click', (e) => {
            if(e.target.className == 'message-close') {
                $message.remove();
            }
        });

        $("#MessagePane").append($message);

        if(params.timeout !== undefined) {
            window.setTimeout(() => {
                $message.remove();
            }, params.timeout * 1000.0);
        }
    },

    // Dark color conversion cache
    darkColorMap: {},
    darkColorElement: null,

    /** Convert the given color to use in dark mode.
     * The color is converted to HSL and the lightness component is inverted to
     * produce the dark mode color.
     */
    getDarkColor: function(color) {
        color = color.trim();

        // Use value from cache if available
        let result = this.darkColorMap[color];
        if(result !== undefined) return result;

        // Convert CSS color to rgb(a) color
        if(this.darkColorElement === null) {
            this.darkColorElement = document.createElement('div');
            this.darkColorElement.id = 'dark-color-element';
            this.darkColorElement.style.display = 'none';
            document.body.appendChild(this.darkColorElement);
        }

        this.darkColorElement.style.color = color;
        const rgbColor = window.getComputedStyle(this.darkColorElement).color;

        // Parse the color
        const m = rgbColor.match(/^rgb(a)?\s*\(\s*([^\)]+)\s*\)/);
        if(!m) {
            console.warn('Cannot parse color "' + color + '" (' + rgbColor + ')');
            return color;
        }

        const hasAlpha = m[1] !== undefined;
        const rgba = m[2].split(',').map(comp => parseFloat(comp));

        if(rgba.length < 3) {
            console.warn('Cannot parse color "' + color + '" (' + rgbColor + ')');
            return color;
        }

        const rgb = rgba.slice(0, 3);

        // Use value from cache if available
        let hsl = this.darkColorMap[rgb];
        if(hsl === undefined) {
            // Convert to HSL
            // https://css-tricks.com/converting-color-spaces-in-javascript/
            function RGBToHSL(r,g,b) {
                // Make r, g, and b fractions of 1
                r /= 255;
                g /= 255;
                b /= 255;

                // Find greatest and smallest channel values
                const cmin = Math.min(r,g,b);
                const cmax = Math.max(r,g,b);
                const delta = cmax - cmin;
                let h = 0, s = 0, l = 0;

                // Calculate hue
                // No difference
                if (delta == 0) h = 0;
                // Red is max
                else if (cmax == r) h = ((g - b) / delta) % 6;
                // Green is max
                else if (cmax == g) h = (b - r) / delta + 2;
                // Blue is max
                else h = (r - g) / delta + 4;

                h = Math.round(h * 60);

                // Make negative hues positive behind 360°
                if (h < 0) h += 360;

                // Calculate lightness
                l = (cmax + cmin) / 2;

                // Calculate saturation
                s = delta == 0 ? 0 : delta / (1 - Math.abs(2 * l - 1));

                // Multiply l and s by 100
                s = +(s * 100).toFixed(1);
                l = +(l * 100).toFixed(1);

                return [h, s, l];
            }

            hsl = RGBToHSL(...rgb);
            // Invert the lightness
            hsl[2] = 100 - hsl[2] * 0.65;

            // Cache the conversion from rgb
            this.darkColorMap[rgb] = hsl;
        }

        result = 'hsl(' + hsl[0] + ' ' + hsl[1] + ' ' + hsl[2] + ' ' +
                (hasAlpha ? ('/ ' + rgba[3]) : '') + ')';

        // Cache the conversion from color text
        this.darkColorMap[color] = result;

        return result;
    },

    setDarkMode: function(enabled) {
        if(enabled) {
            document.body.classList.add('dark-mode');
        } else {
            document.body.classList.remove('dark-mode');
        }

        // Convert the colors in MainText
        document.querySelectorAll('#MainText span[style^="color:"]').forEach(el => {
            if(enabled) {
                if(el.dataset.color === undefined) {
                    el.dataset.color = el.style.color;
                    el.style.color = this.getDarkColor(el.style.color);
                }
            } else {
                if(el.dataset.color !== undefined) {
                    el.style.color = el.dataset.color;
                    delete el.dataset.color;
                }
            }
        });
    },

    bgMusicTimer: -1,

    playBgMusic: function(path) {
        const mplayer = $("#BGMusic")[0];
        if(path === null) {
            // Stop
            mplayer.pause();
        } else {
            let volume = 0;
            mplayer.volume = 0;

            $("#bgmusicsource").attr("src", path);
            mplayer.load();
            mplayer.play();

            // Fade-in effect
            clearInterval(this.bgMusicTimer);
            this.bgMusicTimer = setInterval(function() {
                if(volume >= Settings.musicVolume) {
                    clearInterval(GameUI.bgMusicTimer);
                } else {
                    ++volume;
                    mplayer.volume = volume / 100;
                }
            }, 15);
        }
    },

    playSoundEffect: function(path) {
        const mplayer = $("#SoundEffect")[0];
        if(path === null) {
            // Stop (unused)
            mplayer.pause();
        } else {
            mplayer.src = path;
            mplayer.load();
            mplayer.play();
        }
    },
};
