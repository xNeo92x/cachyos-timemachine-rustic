// SPDX-License-Identifier: MIT
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PC
import org.kde.kirigami as Kirigami
import org.kde.plasma.workspace.dbus as DBus

PlasmoidItem {
    id: root

    property bool autostart: false
    readonly property bool bad: rows.some(r => r.stale || r.last_backup_status === "failed" || r.status === "failed" || r.status === "interrupted" || r.maintenance_error)
    property bool browser: false
    property var entries: []
    property string filter: ""
    property string folder: "/"
    property int generation: 0
    property int lastOpen: 0
    property bool loading: false
    property string message: ""
    property var pending: ({})
    property var rows: []
    readonly property bool running: rows.some(r => r.status === "running")
    property var selected: rows.length ? rows[0] : null
    property string selectedPath: ""
    property string serviceError: ""
    property int snapshotIndex: -1
    property var snapshots: []
    property bool statusPending: false

    function action(command, options, callback, destination) {
        call("Action", [command, destination || (selected ? selected.name : ""), JSON.stringify(options || {})], result => {
            if (!result.ok) {
                message = result.error;
                if (callback)
                    callback(result);
                return;
            }
            pending[result.request] = {
                callback: callback,
                polling: false
            };
            if (!callback)
                message = "Vorgang gestartet …";
            refresh();
        });
    }
    function browse() {
        if (!selected)
            return;
        browser = true;
        snapshots = [];
        entries = [];
        snapshotIndex = -1;
        folder = "/";
        message = "Sicherungen werden gelesen …";
        loading = true;
        const request = ++generation;
        action("snapshots", {}, result => {
            if (request !== generation)
                return;
            loading = false;
            if (!result.ok) {
                message = result.error;
                return;
            }
            snapshots = result.snapshots;
            message = snapshots.length ? "" : "Noch keine Sicherungen vorhanden.";
            snapshotIndex = snapshots.length ? 0 : -1;
            if (snapshotIndex >= 0) {
                folder = snapshots[0].paths.length ? snapshots[0].paths[0] : "/";
                loadFolder();
            }
        });
    }
    function call(member, args, callback) {
        const reply = DBus.SessionBus.asyncCall({
            service: "org.cachyos.TimeMachine",
            path: "/TimeMachine",
            iface: "org.cachyos.TimeMachine",
            member: member,
            arguments: args
        });
        reply.finished.connect(() => {
            let result;
            try {
                result = reply.isError ? {
                    ok: false,
                    error: reply.error.message
                } : JSON.parse(reply.value);
            } catch (e) {
                result = {
                    ok: false,
                    error: String(e)
                };
            }
            callback(result);
            reply.destroy();
        });
    }
    function dialog(kind) {
        call("Dialog", [kind, selected ? selected.name : ""], result => {
            if (!result.ok)
                message = result.error;
            else
                expanded = false;
        });
    }
    function loadFolder() {
        if (snapshotIndex < 0 || !snapshots[snapshotIndex])
            return;
        selectedPath = "";
        entries = [];
        loading = true;
        const request = ++generation;
        action("ls", {
            snapshot: snapshots[snapshotIndex].id,
            path: folder
        }, result => {
            if (request !== generation)
                return;
            loading = false;
            if (!result.ok) {
                message = result.error;
                return;
            }
            entries = result.entries;
            message = "";
        });
    }
    function pollResults() {
        Object.keys(pending).forEach(token => {
            if (pending[token].polling)
                return;
            pending[token].polling = true;
            call("Result", [token], response => {
                if (!pending[token])
                    return;
                pending[token].polling = false;
                if (response.ok === false) {
                    message = response.error;
                    if (pending[token].callback)
                        pending[token].callback(response);
                    delete pending[token];
                } else if (response.done) {
                    const callback = pending[token].callback;
                    delete pending[token];
                    if (callback)
                        callback(response.result);
                    else
                        message = response.result.ok ? "Vorgang abgeschlossen." : response.result.error;
                    refresh();
                }
            });
        });
    }
    function refresh() {
        if (statusPending)
            return;
        statusPending = true;
        call("Status", [], result => {
            statusPending = false;
            if (!result.ok) {
                serviceError = result.error;
                return;
            }
            serviceError = "";
            const name = selected ? selected.name : "";
            rows = result.destinations;
            selected = rows.find(r => r.name === name) || (rows.length ? rows[0] : null);
            autostart = result.autostart;
            if (result.open_requested > lastOpen) {
                lastOpen = result.open_requested;
                expanded = true;
            }
        });
    }
    function restorePath(path) {
        if (!snapshots[snapshotIndex])
            return;
        message = "Wiederherstellung läuft …";
        loading = true;
        action("restore", {
            snapshot: snapshots[snapshotIndex].id,
            path: path
        }, result => {
            loading = false;
            message = result.ok ? "Wiederhergestellt: " + result.restored : result.error;
            if (result.ok)
                Qt.openUrlExternally("file://" + result.target.split("/").map(encodeURIComponent).join("/"));
        });
    }

    Plasmoid.icon: "cachyos-time-machine"
    Plasmoid.status: PlasmaCore.Types.ActiveStatus
    preferredRepresentation: compactRepresentation
    toolTipMainText: "CachyOS Time Machine"
    toolTipSubText: rows.length ? rows.map(r => r.display_name + ": " + r.status_text).join("\n") : "Verschlüsselte Backups mit rustic"

    compactRepresentation: Item {
        implicitHeight: implicitWidth
        implicitWidth: Kirigami.Units.iconSizes.smallMedium

        Kirigami.Icon {
            anchors.fill: parent
            source: "cachyos-time-machine"
        }
        Rectangle {
            anchors.bottom: parent.bottom
            anchors.right: parent.right
            color: root.running ? Kirigami.Theme.highlightColor : root.bad || root.serviceError ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.neutralTextColor
            height: width
            radius: width / 2
            visible: root.running || root.bad || root.serviceError.length > 0 || root.rows.some(r => !r.has_key)
            width: Kirigami.Units.smallSpacing * 2
        }
        MouseArea {
            anchors.fill: parent

            onClicked: root.expanded = !root.expanded
        }
    }
    fullRepresentation: ColumnLayout {
        Layout.minimumHeight: Kirigami.Units.gridUnit * 22
        Layout.minimumWidth: Kirigami.Units.gridUnit * 23
        Layout.preferredHeight: Kirigami.Units.gridUnit * 32
        Layout.preferredWidth: Kirigami.Units.gridUnit * 28
        spacing: Kirigami.Units.smallSpacing

        RowLayout {
            Layout.fillWidth: true

            PC.ToolButton {
                icon.name: "go-previous"
                text: "Zurück"
                visible: root.browser

                onClicked: {
                    root.browser = false;
                    root.generation++;
                    root.loading = false;
                    root.message = "";
                }
            }
            PC.Label {
                Layout.fillWidth: true
                font.bold: true
                text: root.browser ? "Dateien wiederherstellen" : "Time Machine"
            }
            PC.ToolButton {
                icon.name: "configure"
                text: "Einstellungen"

                onClicked: root.dialog("settings")
            }
        }
        PC.Label {
            Layout.fillWidth: true
            color: Kirigami.Theme.negativeTextColor
            text: root.serviceError + "\nBitte python install.py ausführen."
            visible: !!root.serviceError
            wrapMode: Text.Wrap
        }
        PC.ScrollView {
            Layout.fillHeight: true
            Layout.fillWidth: true
            visible: !root.browser

            contentItem: ListView {
                clip: true
                model: root.rows

                delegate: PC.ItemDelegate {
                    required property var modelData

                    highlighted: root.selected && root.selected.name === modelData.name
                    width: ListView.view.width

                    contentItem: ColumnLayout {
                        RowLayout {
                            PC.Label {
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                                font.bold: true
                                text: modelData.display_name
                            }
                            PC.Label {
                                font.pointSize: Kirigami.Theme.smallFont.pointSize
                                opacity: 0.7
                                text: modelData.last_success_text
                            }
                        }
                        PC.Label {
                            opacity: 0.7
                            text: modelData.size_text + " · " + (modelData.snapshot_count === undefined ? "–" : modelData.snapshot_count) + " Snapshots"
                        }
                        PC.Label {
                            Layout.fillWidth: true
                            color: modelData.stale || modelData.status === "failed" ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
                            text: modelData.status_text
                            wrapMode: Text.Wrap
                        }
                        PC.ProgressBar {
                            Layout.fillWidth: true
                            indeterminate: !modelData.progress || modelData.progress.percent_done === undefined
                            value: modelData.progress ? modelData.progress.percent_done || 0 : 0
                            visible: modelData.status === "running"
                        }
                        PC.Label {
                            Layout.fillWidth: true
                            color: Kirigami.Theme.negativeTextColor
                            text: modelData.backup_error || modelData.error || modelData.maintenance_error || ""
                            visible: !!(modelData.backup_error || modelData.error || modelData.maintenance_error)
                            wrapMode: Text.Wrap
                        }
                    }

                    onClicked: root.selected = modelData
                }
            }
        }
        ColumnLayout {
            Layout.fillHeight: true
            Layout.fillWidth: true
            visible: root.browser

            PC.ComboBox {
                Layout.fillWidth: true
                currentIndex: root.snapshotIndex
                enabled: !root.loading
                model: root.snapshots.map(s => new Date(s.time).toLocaleString() + " · " + s.id.substring(0, 8))

                onActivated: {
                    root.snapshotIndex = currentIndex;
                    root.loadFolder();
                }
            }
            RowLayout {
                Layout.fillWidth: true

                PC.ToolButton {
                    enabled: !root.loading && root.folder !== "/"
                    icon.name: "go-up"

                    onClicked: {
                        root.folder = root.folder.substring(0, root.folder.lastIndexOf("/")) || "/";
                        root.loadFolder();
                    }
                }
                PC.TextField {
                    Layout.fillWidth: true
                    enabled: !root.loading
                    text: root.folder

                    onAccepted: {
                        root.folder = text.startsWith("/") ? text : "/" + text;
                        root.loadFolder();
                    }
                }
            }
            PC.TextField {
                Layout.fillWidth: true
                placeholderText: "Dateien filtern …"

                onTextChanged: root.filter = text
            }
            PC.ScrollView {
                Layout.fillHeight: true
                Layout.fillWidth: true

                contentItem: ListView {
                    clip: true
                    model: root.entries.filter(e => e.name.toLowerCase().includes(root.filter.toLowerCase()))

                    delegate: PC.ItemDelegate {
                        required property var modelData

                        enabled: !root.loading
                        highlighted: root.selectedPath === modelData.path
                        icon.name: modelData.type === "dir" ? "folder" : "text-x-generic"
                        text: modelData.name
                        width: ListView.view.width

                        onClicked: root.selectedPath = modelData.path
                        onDoubleClicked: {
                            if (modelData.type === "dir") {
                                root.folder = modelData.path;
                                root.loadFolder();
                            }
                        }
                    }
                }
            }
            PC.BusyIndicator {
                Layout.alignment: Qt.AlignHCenter
                running: root.loading
                visible: root.loading
            }
            RowLayout {
                PC.Button {
                    enabled: !!root.selectedPath && !root.loading
                    text: "Auswahl wiederherstellen"

                    onClicked: root.restorePath(root.selectedPath)
                }
                PC.Button {
                    enabled: root.snapshotIndex >= 0 && !root.loading
                    text: "Diesen Ordner"

                    onClicked: root.restorePath(root.folder)
                }
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            visible: !root.browser

            PC.Label {
                font.bold: true
                text: root.selected ? root.selected.display_name : "Noch kein Backup-Ziel eingerichtet"
            }
            PC.Button {
                Layout.fillWidth: true
                enabled: root.selected && root.selected.has_key && root.selected.status !== "running"
                icon.name: "document-save"
                text: "Jetzt sichern"

                onClicked: root.action("backup")
            }
            PC.Button {
                Layout.fillWidth: true
                enabled: root.selected && root.selected.has_key && root.selected.status !== "running"
                icon.name: "document-revert"
                text: "Dateien wiederherstellen …"

                onClicked: root.browse()
            }
            RowLayout {
                PC.Button {
                    enabled: root.selected && root.selected.has_key && root.selected.status !== "running"
                    text: "Prüfen"

                    onClicked: root.action("check")
                }
                PC.Button {
                    enabled: root.selected && root.selected.has_key && root.selected.status !== "running"
                    text: "Testlauf"

                    onClicked: root.action("backup", {
                        dry_run: true
                    })
                }
                PC.Button {
                    enabled: root.selected && root.selected.status === "running"
                    text: "Abbrechen"

                    onClicked: root.action("cancel")
                }
            }
            RowLayout {
                PC.Button {
                    enabled: !!root.selected
                    text: "Schlüssel …"

                    onClicked: root.dialog("keys")
                }
                PC.Button {
                    enabled: root.selected && root.selected.has_key && root.selected.status !== "running"
                    text: "Initialisieren"

                    onClicked: root.action("init")
                }
                PC.Button {
                    enabled: !!root.selected
                    text: "Protokoll"

                    onClicked: root.dialog("logs")
                }
            }
            RowLayout {
                PC.Button {
                    enabled: !root.running
                    text: "Zeitpläne aktivieren"

                    onClicked: root.action("install")
                }
                PC.Button {
                    enabled: !root.running
                    text: "Pausieren"

                    onClicked: root.action("pause")
                }
            }
            PC.Switch {
                checked: root.autostart
                text: "Autostart bei KDE-Anmeldung"

                onToggled: root.call("Autostart", [checked], result => {
                    if (!result.ok)
                        root.message = result.error;
                    root.refresh();
                })
            }
        }
        PC.Label {
            Layout.fillWidth: true
            elide: Text.ElideRight
            maximumLineCount: 5
            text: root.message
            visible: !!root.message
            wrapMode: Text.Wrap
        }
    }

    Timer {
        interval: root.expanded ? 1000 : 5000
        repeat: true
        running: true
        triggeredOnStart: true

        onTriggered: root.refresh()
    }
    Timer {
        interval: 350
        repeat: true
        running: true

        onTriggered: root.pollResults()
    }
}
