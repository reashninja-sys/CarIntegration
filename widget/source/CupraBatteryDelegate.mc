import Toybox.Lang;
import Toybox.WatchUi;

class CupraBatteryDelegate extends WatchUi.BehaviorDelegate {

    private var _view as CupraBatteryView;

    function initialize(view as CupraBatteryView) {
        BehaviorDelegate.initialize();
        _view = view;
    }

    // Tap or select button → manual refresh
    function onSelect() as Lang.Boolean {
        _view.manualRefresh();
        return true;
    }

    function onMenu() as Lang.Boolean {
        return false;
    }
}
