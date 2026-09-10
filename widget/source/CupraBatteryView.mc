import Toybox.Application;
import Toybox.Communications;
import Toybox.Graphics;
import Toybox.Lang;
import Toybox.Timer;
import Toybox.WatchUi;

class CupraBatteryView extends WatchUi.View {

    private const REFRESH_INTERVAL_MS = 300000; // 5 minutes
    private const CUPRA_RED           = 0xCC0000;

    private var _batteryLevel as Lang.Number?  = null;
    private var _rangeKm      as Lang.Number?  = null;
    private var _charging     as Lang.Boolean  = false;
    private var _timeToFull   as Lang.Number?  = null;  // minutes
    private var _lastUpdated  as Lang.String   = "--:--";
    private var _isLoading    as Lang.Boolean  = false;
    private var _errorMsg     as Lang.String?  = null;
    private var _timer        as Timer.Timer;

    function initialize() {
        View.initialize();
        _timer = new Timer.Timer();
    }

    function onLayout(dc as Graphics.Dc) as Void {}

    function onShow() as Void {
        fetchData();
        _timer.start(method(:onTimerTick), REFRESH_INTERVAL_MS, true);
    }

    function onHide() as Void {
        _timer.stop();
    }

    function onTimerTick() as Void {
        fetchData();
    }

    function manualRefresh() as Void {
        fetchData();
    }

    function fetchData() as Void {
        var rawUrl = Application.Properties.getValue("ServerUrl");
        var serverUrl = (rawUrl instanceof Lang.String) ? rawUrl as Lang.String : "";

        var rawKey = Application.Properties.getValue("ApiKey");
        var apiKey = (rawKey instanceof Lang.String) ? rawKey as Lang.String : "";

        if (serverUrl.length() == 0) {
            _errorMsg = "Set Server URL\nin Garmin Connect";
            _isLoading = false;
            WatchUi.requestUpdate();
            return;
        }
        if (apiKey.length() == 0) {
            _errorMsg = "Set Api Key\nin Garmin Connect";
            _isLoading = false;
            WatchUi.requestUpdate();
            return;
        }

        var base = serverUrl;
        if (base.substring(base.length() - 1, base.length()).equals("/")) {
            base = base.substring(0, base.length() - 1);
        }

        _isLoading = true;
        WatchUi.requestUpdate();

        Communications.makeWebRequest(
            base + "/battery",
            null,
            {
                :method       => Communications.HTTP_REQUEST_METHOD_GET,
                :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON,
                :headers      => {
                    "Accept"    => "application/json",
                    "X-Api-Key" => apiKey,
                },
            },
            method(:onReceive)
        );
    }

    function onReceive(
        responseCode as Lang.Number,
        data         as Lang.Dictionary or Lang.String or Null
    ) as Void {
        _isLoading = false;

        if (responseCode == 200 && data instanceof Lang.Dictionary) {
            var d = data as Lang.Dictionary;

            var batRaw = d["battery_level"];
            _batteryLevel = (batRaw instanceof Lang.Number) ? (batRaw as Lang.Number) : null;

            var rangeRaw = d["range_km"];
            if (rangeRaw instanceof Lang.Number) {
                _rangeKm = rangeRaw as Lang.Number;
            } else if (rangeRaw instanceof Lang.Float) {
                _rangeKm = (rangeRaw as Lang.Float).toNumber();
            } else {
                _rangeKm = null;
            }

            var chVal = d["charging"];
            _charging = (chVal instanceof Lang.Boolean) ? (chVal as Lang.Boolean) : false;

            var ttfRaw = d["time_to_full"];
            _timeToFull = (ttfRaw instanceof Lang.Number) ? (ttfRaw as Lang.Number) : null;

            var luRaw = d["last_updated"];
            _lastUpdated = (luRaw instanceof Lang.String) ? (luRaw as Lang.String) : "--:--";

            _errorMsg = null;

        } else if (responseCode == 403) {
            _errorMsg = "Wrong API key\ncheck settings";
        } else if (responseCode == -1) {
            _errorMsg = "Request timed out";
        } else if (responseCode == -2) {
            _errorMsg = "No connection\nto phone";
        } else if (responseCode == 503) {
            _errorMsg = "Server error\n(check Termux)";
        } else {
            _errorMsg = "HTTP " + responseCode.toString();
        }

        WatchUi.requestUpdate();
    }

    // ----------------------------------------------------------------- drawing

    function onUpdate(dc as Graphics.Dc) as Void {
        var w  = dc.getWidth();
        var h  = dc.getHeight();
        var cx = w / 2;
        var cy = h / 2;

        dc.setColor(Graphics.COLOR_BLACK, Graphics.COLOR_BLACK);
        dc.clear();

        if (_isLoading) {
            _centreText(dc, cx, cy, Graphics.FONT_MEDIUM, "Loading...", Graphics.COLOR_WHITE);
            return;
        }

        if (_errorMsg != null) {
            _centreText(dc, cx, cy - 12, Graphics.FONT_SMALL, _errorMsg as Lang.String, Graphics.COLOR_RED);
            dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
            dc.drawText(cx, cy + 28, Graphics.FONT_XTINY, "Tap to retry", Graphics.TEXT_JUSTIFY_CENTER);
            return;
        }

        // Brand header
        dc.setColor(CUPRA_RED, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, 32, Graphics.FONT_SMALL, "CUPRA", Graphics.TEXT_JUSTIFY_CENTER);

        if (_batteryLevel == null) {
            _centreText(dc, cx, cy, Graphics.FONT_MEDIUM, "No data", Graphics.COLOR_LT_GRAY);
            return;
        }

        var pct   = _batteryLevel as Lang.Number;
        var color = _batteryColor(pct);

        // Large percentage
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, cy - 28, Graphics.FONT_NUMBER_HOT, pct.toString() + "%",
            Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);

        // Battery bar
        _drawBatteryBar(dc, cx, cy + 52, pct, color);

        // Range
        if (_rangeKm != null) {
            dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
            dc.drawText(cx, cy + 76, Graphics.FONT_XTINY,
                (_rangeKm as Lang.Number).toString() + " km range",
                Graphics.TEXT_JUSTIFY_CENTER);
        }

        // Charging + time to full
        if (_charging) {
            dc.setColor(Graphics.COLOR_YELLOW, Graphics.COLOR_TRANSPARENT);
            var chargeLabel = "Charging";
            if (_timeToFull != null) {
                var mins = _timeToFull as Lang.Number;
                var hrs  = mins / 60;
                var rem  = mins % 60;
                chargeLabel = "Charging " + hrs.toString() + "h" + rem.toString() + "m";
            }
            dc.drawText(cx, cy + 92, Graphics.FONT_XTINY, chargeLabel, Graphics.TEXT_JUSTIFY_CENTER);
        }

        // Timestamp
        dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, h - 28, Graphics.FONT_XTINY, "Updated " + _lastUpdated,
            Graphics.TEXT_JUSTIFY_CENTER);
    }

    private function _centreText(
        dc    as Graphics.Dc,
        x     as Lang.Number,
        y     as Lang.Number,
        font  as Graphics.FontType,
        text  as Lang.String,
        color as Lang.Number
    ) as Void {
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        dc.drawText(x, y, font, text,
            Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
    }

    private function _batteryColor(level as Lang.Number) as Lang.Number {
        if (level > 60) { return Graphics.COLOR_GREEN; }
        if (level > 20) { return Graphics.COLOR_YELLOW; }
        return Graphics.COLOR_RED;
    }

    private function _drawBatteryBar(
        dc    as Graphics.Dc,
        cx    as Lang.Number,
        y     as Lang.Number,
        level as Lang.Number,
        color as Lang.Number
    ) as Void {
        var bw   = 100;
        var bh   = 18;
        var tipW = 5;
        var left = cx - bw / 2;
        var top  = y - bh / 2;

        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        dc.drawRectangle(left, top, bw, bh);
        dc.fillRectangle(left + bw, top + bh / 4, tipW, bh / 2);

        var fillW = (bw - 4) * level / 100;
        if (fillW > 0) {
            dc.setColor(color, Graphics.COLOR_TRANSPARENT);
            dc.fillRectangle(left + 2, top + 2, fillW, bh - 4);
        }
    }
}
