
function customproperty() {
    this.Name = "";
    this.Value = "";

    this.cloneForDiff = function() {
        // Only clone the properties that can change
        return {
            Value: this.Value,
        };
    };
}

function SetupCustomPropertyData(GameData) {
    var CurProperty = new customproperty();
    CurProperty.Name = GameData[0];
    CurProperty.Value = GameData[1];
    return CurProperty;
}