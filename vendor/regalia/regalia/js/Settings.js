const Settings = {
    _storageName: function(name) {
        return 'regalia_' + name;
    },

    _get: function(name, defValue) {
        const value = localStorage[this._storageName(name)];
        return value === undefined ? defValue : JSON.parse(value);
    },

    _set: function(name, value) {
        localStorage[this._storageName(name)] = JSON.stringify(value);
    },

    addBoolSetting: function(name, defValue) {
        if(this[name] !== undefined) {
            throw new Error('Setting with name "' + name + '" already exists!');
        }

        let value = this._get(name, !!defValue);
        Object.defineProperty(this, name, {
            get() {
                return value;
            },
            set(newValue) {
                this._set(name, value = !!newValue);
            },
            enumerable: true,
        });
    },

    addIntSetting: function(name, defValue) {
        if(this[name] !== undefined) {
            throw new Error('Setting with name "' + name + '" already exists!');
        }

        function parseIntSafe(value) {
            let num = parseInt(value);
            return isNaN(num) ? 0 : num;
        }

        let value = parseIntSafe(this._get(name, defValue));
        Object.defineProperty(this, name, {
            get() {
                return value;
            },
            set(newValue) {
                this._set(name, value = parseIntSafe(newValue));
            },
            enumerable: true,
        });
    },
};

Settings.addBoolSetting('historyEnabled', false);
Settings.addIntSetting('historySize', 100);

Settings.addIntSetting('musicVolume', 100);
Settings.addIntSetting('sfxVolume', 100);

Settings.addBoolSetting('debugEnabled', false);

Settings.addBoolSetting('darkMode', window.matchMedia &&
        window.matchMedia('(prefers-color-scheme: dark)').matches);
