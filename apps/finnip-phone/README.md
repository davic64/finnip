# Finnip para Android

APK que deja un celular viejo como bocina con pantalla de Finnip:
- Abre la app web (`?phone=1`) a pantalla completa y siempre escucha "Finnip".
- La pantalla nunca se apaga. En reposo baja al mínimo el brillo de su propia ventana.

## Compilar
Necesita Java 17 y el SDK de Android (plataforma 35):

```sh
brew install openjdk@17 && brew install --cask android-commandlinetools
export JAVA_HOME=$(brew --prefix openjdk@17)/libexec/openjdk.jdk/Contents/Home ANDROID_HOME=$HOME/Library/Android/sdk
sdkmanager --sdk_root=$ANDROID_HOME "platforms;android-35" "build-tools;35.0.0" "platform-tools"
./gradlew assembleDebug -PfinnipUrl=https://finnip.<tu-tailnet>.ts.net
```

`finnipUrl` es la dirección HTTPS del gateway en tu tailnet. Se fija al compilar y no se guarda en el repo.

## Instalar
1. En el celular instala Tailscale e inicia sesión en la misma tailnet.
2. Activa la depuración USB. En MIUI activa también "Instalar vía USB".
3. Instala el APK: `adb install -r app/build/outputs/apk/debug/app-debug.apk`
4. Abre Finnip y permite el micrófono.
5. Para modo kiosco, elige Finnip como app de inicio: Ajustes → Aplicaciones → Aplicaciones predeterminadas → Pantalla de inicio.
