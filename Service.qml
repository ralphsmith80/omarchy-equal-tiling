import QtQuick
import Quickshell

Item {
    Component.onCompleted: {
        const script = decodeURIComponent(Qt.resolvedUrl("service.py").toString().replace(/^file:\/\//, ""))
        // A detached worker can finish cleanup even when removal deletes this QML.
        // It watches Omarchy's enabled state and the compositor connection.
        Quickshell.execDetached(["python3", "-B", script])
    }
}
