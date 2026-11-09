define([], function () {
    'use strict';

    var PLUGIN_ID = '2fea54cd-3c4a-4307-ab53-5e25a07a24ec';

    function number(value, fallback, min, max) {
        var n = parseInt(value, 10);
        if (isNaN(n)) { n = fallback; }
        return Math.min(max, Math.max(min, n));
    }

    function Controller(view) {
        var self = this;
        this.view = view;
        this.find = function (id) { return view.querySelector('#' + id); };

        this.find('pmTest').addEventListener('click', function (e) {
            e.preventDefault();
            self.test();
        });
        this.find('PrerollsMaxConfigForm').addEventListener('submit', function (e) {
            e.preventDefault();
            self.save();
            return false;
        });
    }

    Controller.prototype.showTest = function (ok, message) {
        var el = this.find('pmTestResult');
        el.style.display = 'block';
        el.style.background = ok ? 'rgba(39,174,96,0.15)' : 'rgba(231,76,60,0.15)';
        el.style.border = '1px solid ' + (ok ? 'rgba(39,174,96,0.4)' : 'rgba(231,76,60,0.4)');
        el.textContent = message;
    };

    Controller.prototype.load = function () {
        var f = this.find;
        ApiClient.getPluginConfiguration(PLUGIN_ID).then(function (cfg) {
            f('pmUrl').value = cfg.PrerollsMaxUrl || '';
            f('pmKey').value = cfg.ApiKey || '';
            f('pmMovies').checked = cfg.EnableForMovies !== false;
            f('pmEpisodes').checked = cfg.EnableForEpisodes !== false;
            f('pmTimeout').value = cfg.TimeoutSeconds || 3;
            f('pmBinge').value = cfg.BingeWindowHours || 4;
            f('pmCache').value = cfg.MaxCacheMegabytes || 2048;
            f('pmFrom').value = cfg.PathPrefixFrom || '';
            f('pmTo').value = cfg.PathPrefixTo || '';
        });
    };

    Controller.prototype.test = function () {
        var self = this;
        self.showTest(true, 'Checking...');
        ApiClient.ajax({
            type: 'POST',
            url: ApiClient.getUrl('PrerollsMax/Test'),
            data: JSON.stringify({ PrerollsMaxUrl: self.find('pmUrl').value.trim(), ApiKey: self.find('pmKey').value.trim() }),
            contentType: 'application/json',
            dataType: 'json'
        }).then(function (r) {
            self.showTest(!!(r.Ok || r.ok), r.Message || r.message || 'No answer.');
        }, function () {
            self.showTest(false, 'Emby could not run the test. Restart Emby after installing the plugin, then try again.');
        });
    };

    Controller.prototype.save = function () {
        var f = this.find;
        ApiClient.getPluginConfiguration(PLUGIN_ID).then(function (cfg) {
            cfg.PrerollsMaxUrl = f('pmUrl').value.trim().replace(/\/+$/, '');
            cfg.ApiKey = f('pmKey').value.trim();
            cfg.EnableForMovies = f('pmMovies').checked;
            cfg.EnableForEpisodes = f('pmEpisodes').checked;
            cfg.TimeoutSeconds = number(f('pmTimeout').value, 3, 1, 30);
            cfg.BingeWindowHours = number(f('pmBinge').value, 4, 1, 48);
            cfg.MaxCacheMegabytes = number(f('pmCache').value, 2048, 256, 1048576);
            cfg.PathPrefixFrom = f('pmFrom').value.trim();
            cfg.PathPrefixTo = f('pmTo').value.trim();
            ApiClient.updatePluginConfiguration(PLUGIN_ID, cfg).then(function () {
                f('pmSaveResult').textContent = 'Saved.';
                try { Dashboard.processPluginConfigurationUpdateResult(); } catch (e) { }
            }, function () {
                f('pmSaveResult').textContent = 'Not saved. Emby refused the change; are you signed in as an administrator?';
            });
        });
    };

    Controller.prototype.onResume = function () { this.load(); };
    Controller.prototype.onPause = function () { };

    return Controller;
});
