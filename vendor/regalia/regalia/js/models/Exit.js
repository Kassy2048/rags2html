
function exit() {
    this.Direction = "Empty";
    this.bActive = false;
    this.DestinationRoom = "";
    this.PortalObjectName = "<None>";

    this.cloneForDiff = function() {
        // Only clone the properties that can change
        return {
            bActive: this.bActive,
            DestinationRoom: this.DestinationRoom,
            PortalObjectName: this.PortalObjectName,
        };
    };
}

function SetupExitData(GameData) {
    var CurExit = new exit();
    CurExit.Direction = GameData[0];
    CurExit.bActive = GameData[1];
    CurExit.DestinationRoom = GameData[2];
    CurExit.PortalObjectName = GameData[3];
    return CurExit;
}