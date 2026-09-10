import Toybox.Application;
import Toybox.Lang;
import Toybox.WatchUi;

class CupraBatteryApp extends Application.AppBase {

    private var _view as CupraBatteryView;

    function initialize() {
        AppBase.initialize();
    }

    function onStart(state as Lang.Dictionary?) as Void {}
    function onStop(state as Lang.Dictionary?) as Void {}

    function getInitialView() as [WatchUi.Views] or [WatchUi.Views, WatchUi.InputDelegates] {
        _view = new CupraBatteryView();
        var delegate = new CupraBatteryDelegate(_view);
        return [_view, delegate];
    }
}
