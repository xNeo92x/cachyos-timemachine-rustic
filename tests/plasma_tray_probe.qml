// Test-only block inserted into the applet root by plasma_smoke.sh.
// Exercise KDE's real tray delegate and popup container, not a desktop widget.
Timer {
    interval: 500
    repeat: true
    running: true
    property int step: 0
    property var delegate: null
    property var tray: null

    function check(condition, message) {
        if (!condition)
            throw new Error("TIMEMACHINE_TEST_FAILED: " + message);
    }
    function click() {
        const event = {button: Qt.LeftButton};
        delegate.pressed(event);
        delegate.clicked(event);
    }
    function checkPopup() {
        check(root.expanded, "applet expanded");
        check(tray.systemTrayState.activeApplet === root, "tray selected the applet");
        check(tray.systemTrayState.expanded, "tray popup expanded");
        check(root.fullRepresentationItem && root.fullRepresentationItem.visible,
              "full representation is visible in tray popup");
    }
    onTriggered: {
        if (step === 0) {
            for (let item = root.parent; item; item = item.parent) {
                if (item.applet === root)
                    delegate = item;
                if (item.systemTrayState)
                    tray = item;
            }
            const compact = root.compactRepresentationItem;
            if (!delegate || !tray || !compact || root.statusPending)
                return;
            check(!root.preferredRepresentation, "no forced representation blocking tray popup");
            const icon = compact.children.find(item => item.objectName === "timeMachineTrayIcon");
            check(icon && icon.status === Image.Ready && icon.paintedWidth > 0,
                  "production SVG icon loaded and sized");
            console.info("TIMEMACHINE_ICON_READY");
            console.info("TIMEMACHINE_TRAY_READY");
            root.expanded = false;
        } else if (step === 1) {
            click();
        } else if (step === 2) {
            checkPopup();
            console.info("TIMEMACHINE_POPUP_READY");
            console.info("TIMEMACHINE_CLICK_READY");
            click();
        } else if (step === 3) {
            check(!root.expanded && !tray.systemTrayState.expanded, "second click closed the popup");
            console.info("TIMEMACHINE_CLOSE_READY");
            Plasmoid.activated();
        } else if (step === 4) {
            checkPopup();
            console.info("TIMEMACHINE_ACTIVATE_READY");
            stop();
        }
        step++;
    }
}
