
function statusbaritem() {
    this.Name = "";
    this.Text = "";
    this.bVisible = true;
    this.width = 0;

    this.cloneForDiff = function() {
        // Only clone the properties that can change
        return {
            bVisible: this.bVisible,
        };
    };
}

function SetupStatusBarData(GameData) {
    var TheStatusBarItem = new statusbaritem();
    TheStatusBarItem.Name = GameData[0];
    TheStatusBarItem.Text = GameData[1];
    TheStatusBarItem.bVisible = GameData[2];
    TheStatusBarItem.width = GameData[3];
    return TheStatusBarItem;
}