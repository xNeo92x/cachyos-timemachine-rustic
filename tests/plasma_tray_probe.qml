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
    property bool progressObserved: false
    property string expectedLanguage: "en"

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
    function fullyVisible(item) {
        const popup = root.fullRepresentationItem;
        check(item && item.visible && item.width > 0 && item.height > 0, "item has visible geometry");
        const point = item.mapToItem(popup, 0, 0);
        check(point.x >= -1 && point.y >= -1 && point.x + item.width <= popup.width + 1 &&
              point.y + item.height <= popup.height + 1, "whole item fits the compact popup: " + item.objectName);
        for (let parent = item.parent; parent && parent !== popup; parent = parent.parent) {
            if (parent.clip) {
                const local = item.mapToItem(parent, 0, 0);
                check(local.y >= -1 && local.y + item.height <= parent.height + 1,
                      "no scroll viewport clips the metrics: " + item.objectName);
            }
        }
    }
    function checkButtons() {
        const popup = root.fullRepresentationItem;
        const names = ["backupNowButton", "backupRestoreButton", "backupCancelButton", "backupMoreButton"];
        const buttons = names.map(name => findButton(popup, name));
        buttons.forEach(button => fullyVisible(button));
        check(Math.abs(buttons[0].width - buttons[1].width) < 1 &&
              Math.abs(buttons[2].width - buttons[3].width) < 1, "action columns have equal width");
        check(buttons[0].width + buttons[1].width > popup.width * 0.95,
              "actions use the available popup width");
        check(buttons[0].mapToItem(popup, 0, 0).x < buttons[1].mapToItem(popup, 0, 0).x,
              "actions are arranged in two columns");
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
            // Reproduce the small viewport in the user's screenshot instead
            // of accepting labels that exist underneath a clipped ScrollView.
            root.fullRepresentationItem.width = 420;
            root.fullRepresentationItem.height = 380;
        } else if (step === 5) {
            const backup = findButton(root.fullRepresentationItem, "backupNowButton");
            check(root.language === expectedLanguage && backup.text === root.tr("Jetzt sichern"), "popup follows saved language");
            checkButtons();
            console.info("TIMEMACHINE_LOCALIZED_UI_READY");
            check(root.selected && !root.selected.has_key, "test destination has no password");
            check(backup && backup.enabled, "backup enabled without optional password");
            check(trayInput.mouseClick(backup, backup.width / 2, backup.height / 2,
                                      Qt.LeftButton, Qt.NoModifier, 10), "backup click delivered");
        } else if (step === 6) {
            check(!root.selected.backup_error, "popup backup did not fail: " + root.selected.backup_error);
            const live = root.selected.progress_view;
            if (root.selected.status === "running" && live && live.percent > 0 && live.percent < 1 &&
                    root.selected.progress.bytes_per_second > 0) {
                const bar = findButton(root.fullRepresentationItem, "backupLiveProgressBar");
                const detail = findButton(root.fullRepresentationItem, "backupLiveProgressDetails");
                const speed = findButton(root.fullRepresentationItem, "backupLiveProgressSpeed");
                const timing = findButton(root.fullRepresentationItem, "backupLiveProgressTiming");
                check(bar && bar.visible && !bar.indeterminate && Math.abs(bar.value - live.percent) < 0.001,
                      "live progress bar shows native fraction");
                check(detail && detail.visible && detail.text.includes("%") && detail.text.includes("/"),
                      "processed and total source bytes visible");
                check(speed && speed.visible && speed.text.includes(root.tr("Verarbeitung (Ø): {p0}").split("{p0}")[0]) && speed.text.includes("/s"),
                      "live source processing rate visible");
                [bar, detail, speed, timing].forEach(item => fullyVisible(item));
                checkButtons();
                if (!progressObserved) {
                    console.info("TIMEMACHINE_LIVE_PROGRESS_READY");
                    console.info("TIMEMACHINE_COMPACT_LAYOUT_READY");
                }
                progressObserved = true;
            }
            if (!root.selected.last_success || root.selected.status === "running")
                return;
            check(progressObserved, "real backup showed live progress before completion");
            console.info("TIMEMACHINE_PASSWORDLESS_BACKUP_READY");
            const more = findButton(root.fullRepresentationItem, "backupMoreButton");
            check(trayInput.mouseClick(more, more.width / 2, more.height / 2,
                                      Qt.LeftButton, Qt.NoModifier, 10), "more actions click delivered");
        } else if (step === 7) {
            const menu = root.fullRepresentationItem.actionsMenu;
            check(menu.opened && menu.count === 9, "maintenance actions remain accessible in the menu");
            const key = menu.itemAt(3);
            check(key && key.enabled && key.objectName === "backupKeyButton", "password menu item enabled");
            check(trayInput.mouseClick(key, key.width / 2, key.height / 2,
                                      Qt.LeftButton, Qt.NoModifier, 10), "password menu click delivered");
            console.info("TIMEMACHINE_ACTION_MENU_READY");
        } else if (step === 8) {
            root.call("Status", [], result => {
                check(result.key_dialog_visible, "password window visible after popup handoff");
                console.info("TIMEMACHINE_KEY_DIALOG_READY");
                stop();
            });
        }
        step++;
    }
}
