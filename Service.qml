import QtQuick
import Quickshell
// Registers ProcessContext for execDetached's object argument.
import Quickshell.Io

Item {
    Component.onCompleted: {
        const script = decodeURIComponent(Qt.resolvedUrl("service.py").toString().replace(/^file:\/\//, ""))
        // A detached worker can finish cleanup even when removal deletes this QML.
        // It watches Omarchy's enabled state and the compositor connection.
        const environment = { PATH: "/usr/bin", LC_ALL: "C.UTF-8" }
        // Pass session paths only. Build, loader, and Python controls are excluded.
        for (const name of ["HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR",
                            "HYPRLAND_INSTANCE_SIGNATURE", "DBUS_SESSION_BUS_ADDRESS"]) {
            const value = Quickshell.env(name)
            if (value) environment[name] = value
        }
        Quickshell.execDetached({
            command: ["/usr/bin/python3", "-E", "-S", "-B", script],
            environment: environment,
            clearEnvironment: true,
            workingDirectory: "/"
        })
    }
}
