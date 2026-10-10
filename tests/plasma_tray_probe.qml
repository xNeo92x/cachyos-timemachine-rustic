// Test-only block inserted into the applet root by plasma_smoke.sh.
// Exercise KDE's real tray delegate and popup container, not a desktop widget.
TestEvent { id: trayInput }
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
        check(trayInput.mouseClick(delegate, delegate.width / 2, delegate.height / 2,
                                  Qt.LeftButton, Qt.NoModifier, 10), "mouse click delivered");
    }
    function checkPopup() {
        check(root.expanded, "applet expanded");
        check(tray.systemTrayState.activeApplet === root, "tray selected the applet");
        check(tray.systemTrayState.expanded, "tray popup expanded");
        check(root.fullRepresentationItem && root.fullRepresentationItem.visible,
              "full representation is visible in tray popup");
    }
    function findButton(item, name) {
        if (item.objectName === name)
            return item;
        for (const child of item.children) {
            const found = findButton(child, name);
            if (found)
                return found;
        }
        return null;
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
        } else if (step === 5) {
            const backup = findButton(root.fullRepresentationItem, "backupNowButton");
            check(root.selected && !root.selected.has_key, "test destination has no password");
            check(backup && backup.enabled, "backup enabled without optional password");
            check(trayInput.mouseClick(backup, backup.width / 2, backup.height / 2,
                                      Qt.LeftButton, Qt.NoModifier, 10), "backup click delivered");
        } else if (step === 6) {
            check(!root.selected.backup_error, "popup backup did not fail: " + root.selected.backup_error);
            if (!root.selected.last_success || root.selected.status === "running")
                return;
            console.info("TIMEMACHINE_PASSWORDLESS_BACKUP_READY");
            const key = findButton(root.fullRepresentationItem, "backupKeyButton");
            check(key && key.enabled, "password button enabled");
            check(trayInput.mouseClick(key, key.width / 2, key.height / 2,
                                      Qt.LeftButton, Qt.NoModifier, 10), "password click delivered");
        } else if (step === 7) {
            root.call("Status", [], result => {
                check(result.key_dialog_visible, "password window visible after popup handoff");
                console.info("TIMEMACHINE_KEY_DIALOG_READY");
                stop();
            });
        }
        step++;
    }
}
