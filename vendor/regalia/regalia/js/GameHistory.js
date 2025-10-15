const GameHistory = {
    MAX_HISTORY_SIZE: 100,  // Erased by user settings
    states: [],
    /** Deep copy of TheGame when last state was saved */
    oldGameData: null,
    oldTextChild: null,
    oldImage: null,
    enabled: false,

    reset: function() {
        this.states = [];
        this.oldGameData = null;
        this.oldTextChild = null;
        this.oldImage = null;
    },

    _saveOldInfo: function(gameData) {
        if(gameData === undefined) {
            // Clone current game data
            gameData = GameCloneForDiff(TheGame);
        }
        this.oldGameData = gameData;
        // Save last text history element
        this.oldTextChild = document.getElementById('MainText').lastChild;
        // Save current media
        this.oldImage = Globals.currentImage;
    },

    pushState: function() {
        if(!this.enabled) return;

        const gameData = GameCloneForDiff(TheGame);

        if(this.oldGameData !== null) {
            while(this.states.length >= this.MAX_HISTORY_SIZE) {
                this.states.shift();
            }

            const start2 = window.performance.now();

            // Save info to revert this state
            const state = {
                // Save the game data changes
                gameChanges: DeepDiff.diff(gameData, this.oldGameData),
                textChild: this.oldTextChild,
                currentImage: this.oldImage,
            };

            this.states.push(state);
        }

        this._saveOldInfo(gameData);
    },

    popState: function() {
        if(!this.canGoBack()) return false;

        const state = this.states.pop();

        // Remove elements after last text history element
        if(state.textChild.parent === null) {
            // Text history has been truncated too much
            $('#MainText').html('');
        } else {
            while(state.textChild.nextSibling) {
                state.textChild.nextSibling.remove();
            }
        }

        // Revert state changed
        if(state.gameChanges !== undefined) {
            // gameChanges can be undefined if only text changed
            orderChanges(state.gameChanges).forEach((change) => {
                DeepDiff.applyChange(TheGame, true, change);
            });
        }

        RoomChange(false, false, true);
        // Restore current media
        if(state.currentImage !== undefined) {
            // This must be done after the call to RoomChange() because it changes the image
            showImage(state.currentImage);
        }
        UpdateStatusBars();
        SetPortrait(TheGame.Player.PlayerPortrait);
        $("#playernamechoice").css("visibility", "hidden");
        $("#textactionchoice").css("visibility", "hidden");
        $("#textchoice").css("visibility", "hidden");
        $("#inputmenu").css("visibility", "hidden");
        $("#selectionmenu").css("visibility", "hidden");
        $("#genderchoice").css("visibility", "hidden");
        $("#cmdinputmenu").css("visibility", "hidden");
        $("#Continue").css("background-color", "rgb(128, 128, 128)");
        $("#Continue").css('visibility', "hidden");
        GameUI.showGameElements();

        this._saveOldInfo();

        return true;
    },

    size: function() {
        return this.states.length;
    },

    canGoBack: function() {
        return this.states.length > 0;
    },

    noGoBackReason: function() {
        if (!this.enabled) return 'History is disabled';
        if (this.states.length == 0) return 'History is empty';
        return '';
    },
};

GameHistory.reset();
