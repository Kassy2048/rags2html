var TheGame = null;
var OriginalGame = null;

var Globals = {
    bRunningTimers: false,
    bMasterTimer: false,
    bCancelMove: false,
    curActions: undefined,
    currentImage: "",
    loopArgs: {
        object: null,
        idx: 0,
        array: null,
        prevObject: null
    },
    loopArgsValid: false,
    inputDataObject: null,
    movingDirection: "",
    runningLiveTimerCommands: false,
    theObj: null,
    selectedObj: null,
    variableGettingSet: null
};

function ResetLoopObjects(backup) {
    Globals.loopArgs = {
        array: null,
        idx: 0,
        object: null,
        prevObject: backup ? Globals.loopArgs.object : null
    };
    Globals.loopArgsValid = false;
}

function RestoreLoopObject() {
    Globals.loopArgs.object = Globals.loopArgs.prevObject;
    Globals.loopArgs.prevObject = null;
}
