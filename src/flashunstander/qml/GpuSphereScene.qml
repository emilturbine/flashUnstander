import QtQuick
import QtQuick.Shapes

Item {
    Item {
        anchors.fill: parent
        z: -100000

        Repeater {
            model: scene.orbits.length
            Shape {
                required property int index
                readonly property var orbit: scene.orbits[index]
                anchors.fill: parent
                ShapePath {
                    fillColor: "transparent"
                    strokeColor: orbit.color
                    strokeWidth: orbit.lineWidth
                    joinStyle: ShapePath.RoundJoin
                    PathPolyline { path: orbit.points }
                }
            }
        }
    }

    Repeater {
        model: scene.frame.length
        ShaderEffect {
            required property int index
            readonly property var body: scene.frame[index] || ({})
            visible: !!body.diameter
            x: body.px || 0
            y: body.py || 0
            width: body.diameter || 0
            height: body.diameter || 0
            z: body.depth || 0
            opacity: body.alpha || 0
            property real extent: body.extent || 1
            property real spin: body.spin || 0
            property real tilt: body.tilt || 0
            property real axialTip: body.axialTip || 0
            property real selfLit: body.selfLit || 0
            property real terrestrial: body.terrestrial || 0
            property real materialKind: body.kind || 0
            readonly property string textureKey: body.texture || ""
            readonly property bool loadTexture: textureKey !== "" && scene.preloads.includes(textureKey)
            readonly property bool loadComplete: loadTexture
                && (surface.status === Image.Ready || surface.status === Image.Error)
                && (!terrestrial || weatherMap.status === Image.Ready || weatherMap.status === Image.Error)
            property real surfaceReady: surface.status === Image.Ready ? 1 : 0
            Behavior on surfaceReady { NumberAnimation { duration: 180 } }
            property real detailLevel: body.detailLevel || 0
            Behavior on detailLevel { NumberAnimation { duration: 160 } }
            property real weatherDrift: body.weatherDrift || 0
            property real cirrusDrift: body.cirrusDrift || 0
            property real weatherEvolution: body.weatherEvolution || 0
            property real stormOrigin: body.stormOrigin || 0
            property vector4d storm0: body.storm0 || Qt.vector4d(0, 0, 0, 0)
            property vector4d storm1: body.storm1 || Qt.vector4d(0, 0, 0, 0)
            property vector4d storm2: body.storm2 || Qt.vector4d(0, 0, 0, 0)
            property var weather: terrestrial ? weatherMap : surface
            property real weatherReady: terrestrial && surface.status === Image.Ready
                                        && weatherMap.status === Image.Ready ? 1 : 0
            Behavior on weatherReady { NumberAnimation { duration: 240 } }

            onLoadCompleteChanged: {
                if (loadComplete) {
                    const key = textureKey
                    Qt.callLater(() => scene.detailReady(key))
                }
            }
            property var surface: Image {
                source: loadTexture ? "image://planet/" + textureKey : ""
                visible: false
                asynchronous: true
                smooth: true
                mipmap: true
            }
            Image {
                id: weatherMap
                source: terrestrial && loadTexture ? "image://planet/" + textureKey + "/weather" : ""
                visible: false
                asynchronous: true
                smooth: true
                mipmap: true
            }
            property vector3d light: Qt.vector3d(body.lx || 0, body.ly || 0, body.lz || 0)
            property real brightness: body.brightness || 0
            property real shadowLight: body.shadowLight || 0
            property vector4d ringPattern: body.ringPattern || Qt.vector4d(0, 0, 0, 0)
            property real ringSeed: body.ringSeed || 0
            property real ringPhase: body.ringPhase || 0
            property real ringReflectivity: body.ringReflectivity || 0
            property vector3d ringColor: Qt.vector3d(body.rr || 0, body.rg || 0, body.rb || 0)
            fragmentShader: "sphere.frag.qsb"
        }
    }
}
