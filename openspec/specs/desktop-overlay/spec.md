# desktop-overlay Specification

## Purpose
Mantener a Finnip presente en el escritorio de macOS como una capa inmersiva sobre lo que el usuario tenga en pantalla: invisible en reposo, y mostrando el holograma, los paneles y los avisos solo cuando habla, escucha o tiene algo que comunicar.

## Requirements

### Requirement: Ventana overlay que no estorba
La app SHALL mostrar a Finnip en una ventana transparente, sin bordes ni sombra, que cubre la pantalla elegida (ver "Pantalla elegible") y queda por encima de las demás ventanas, también en todos los Espacios. La ventana MUST dejar pasar siempre los clics y el teclado a las apps de debajo, y MUST NOT aparecer en el Dock ni en el selector de apps.

#### Scenario: Trabajar con Finnip visible
- **WHEN** el holograma está en pantalla y el usuario hace clic sobre la zona donde se dibuja
- **THEN** el clic llega a la app que está debajo, como si el overlay no existiera

#### Scenario: Cambiar de Espacio
- **WHEN** el usuario cambia a otro Espacio de macOS
- **THEN** Finnip sigue disponible en ese Espacio sin abrir otra ventana

### Requirement: Reposo invisible
Cuando Finnip está en reposo (esperando "Finnip") o silenciado, la app SHALL NOT mostrar nada en pantalla y MUST NOT dibujar el holograma, para no gastar GPU mientras no se ve.

#### Scenario: Nadie le habla
- **WHEN** termina una respuesta y Finnip vuelve a reposo
- **THEN** el holograma se desvanece y la animación se detiene hasta el siguiente despertar

### Requirement: Holograma flotante al despertar y al hablar
Al despertarla con "Finnip", mientras escucha, piensa o habla, y cuando da un aviso por su cuenta, la app SHALL mostrar el holograma flotando en una esquina de la pantalla, sin tapar el centro.

#### Scenario: Despertar con la voz
- **WHEN** el usuario dice "Finnip, ¿qué hora es?" con la app en reposo
- **THEN** el holograma aparece en la esquina, escucha, responde con voz y vuelve a reposo al terminar

#### Scenario: Aviso de la impresora
- **WHEN** el gateway envía un aviso ("es momento de meter el filamento") sin que el usuario haya hablado
- **THEN** el holograma aparece en la esquina mientras dice el aviso y luego vuelve a reposo

### Requirement: Escena central con fondo oscurecido
Cuando Finnip muestra el estado del servidor o la agenda, la app SHALL llevar el holograma y el panel al centro y oscurecer el resto de la pantalla con una capa semitransparente. La escena MUST terminar sola cuando el panel se oculta.

#### Scenario: Estado del servidor
- **WHEN** el usuario pregunta "¿cómo está el servidor?"
- **THEN** el fondo se oscurece, aparecen al centro las métricas y el holograma, y al ocultarse el panel la pantalla vuelve a la normalidad

#### Scenario: Agenda
- **WHEN** el usuario pregunta "¿qué tengo esta semana?"
- **THEN** la agenda aparece al centro sobre el fondo oscurecido mientras Finnip la lee

### Requirement: Aviso de música pasajero
Cuando empieza a sonar algo en la bocina o cambia la canción, la app SHALL mostrar un aviso con título, artista y volumen, que se desvanece solo tras unos segundos. Pausar la música o que siga la misma canción MUST NOT volver a mostrarlo.

#### Scenario: Cambio de canción
- **WHEN** la bocina pasa a reproducir una canción distinta
- **THEN** aparece el aviso de "reproduciendo" con la canción y el volumen, y desaparece solo

#### Scenario: Música pausada
- **WHEN** el usuario pausa la música
- **THEN** no aparece ningún aviso de música

### Requirement: Tarjetas breves de dispositivos
Cuando cambia un dispositivo del hogar, la app SHALL mostrar su tarjeta de acción de forma breve, sin oscurecer la pantalla.

#### Scenario: Luz encendida
- **WHEN** el usuario dice "Finnip, prende la lámpara"
- **THEN** aparece brevemente la tarjeta de la lámpara encendida junto al holograma

### Requirement: Micrófono siempre en reposo con wake word
Al abrirse, la app SHALL abrir el micrófono en modo conversación y quedarse en reposo, despertando solo con una frase que empiece con "Finnip". Las reglas de reposo existentes (incluido volver a reposo mientras suena música) MUST aplicarse igual que en la interfaz web.

#### Scenario: Primer arranque
- **WHEN** la app se abre por primera vez
- **THEN** macOS pide permiso de micrófono una vez, y después la app queda en reposo esperando "Finnip"

#### Scenario: Música sonando
- **WHEN** suena música en la bocina y el usuario no dice "Finnip"
- **THEN** Finnip sigue en reposo y no aparece en pantalla

### Requirement: Interrumpir mientras habla
Mientras Finnip habla, el usuario SHALL poder callarlo en cualquier momento: con el atajo global, o diciendo una frase que empiece con "Finnip". "Finnip" solo, o seguido de "para", "cállate" o "basta", MUST detener la respuesta sin enviar nada al asistente. "Finnip" seguido de otra petición MUST detener la respuesta y atender la nueva. La propia voz de Finnip saliendo por las bocinas MUST NOT interrumpirlo, aunque diga "Finnip".

#### Scenario: Callarlo con la voz
- **WHEN** Finnip está leyendo la agenda y el usuario dice "Finnip, para"
- **THEN** deja de hablar de inmediato y queda escuchando, sin enviar "para" al asistente

#### Scenario: Cambiar de tema a media respuesta
- **WHEN** Finnip está respondiendo y el usuario dice "Finnip, ¿qué hora es?"
- **THEN** corta la respuesta anterior y contesta la hora

#### Scenario: Callarlo con el atajo
- **WHEN** Finnip está hablando y el usuario presiona el atajo global
- **THEN** deja de hablar de inmediato

#### Scenario: Su propia voz
- **WHEN** Finnip dice "Soy Finnip, su asistente" por las bocinas
- **THEN** la respuesta continúa sin interrumpirse

### Requirement: Controles de barra de menú, atajo y arranque
La app SHALL tener un ícono en la barra de menú con mostrar u ocultar Finnip, silenciar u oír el micrófono, elegir la pantalla, abrir Preferencias y salir. Un atajo de teclado global (⌥⌘F por defecto, personalizable) SHALL despertar a Finnip para hablar sin decir su nombre, o silenciarlo si ya escucha. La app SHALL iniciarse sola al abrir sesión, con opción para desactivarlo.

#### Scenario: Silenciar desde la barra de menú
- **WHEN** el usuario elige "Silenciar micrófono" en el menú
- **THEN** la app deja de escuchar, Finnip desaparece de la pantalla y el ícono muestra que está silenciado

#### Scenario: Hablar con el atajo
- **WHEN** el usuario presiona el atajo global con Finnip en reposo
- **THEN** el holograma aparece escuchando y la siguiente frase se atiende sin decir "Finnip"

### Requirement: Pantalla elegible
La barra de menú SHALL listar las pantallas conectadas y permitir elegir en cuál aparece Finnip; por defecto, la principal. La elección MUST guardarse entre reinicios. Si la pantalla elegida se desconecta, Finnip SHALL pasar a la principal y regresar sola a la elegida cuando se reconecte.

#### Scenario: Elegir otro monitor
- **WHEN** el usuario elige su segundo monitor en el menú "Pantalla"
- **THEN** a partir de ese momento el holograma, los paneles y el fondo oscurecido aparecen en ese monitor, también después de reiniciar la app

#### Scenario: Monitor desconectado
- **WHEN** se desconecta el monitor elegido
- **THEN** Finnip aparece en la pantalla principal, y al reconectarlo vuelve a ese monitor sin que el usuario haga nada

### Requirement: Atajo personalizable
Una ventana de Preferencias, abierta desde la barra de menú, SHALL mostrar el atajo actual y permitir cambiarlo presionando la nueva combinación, que MUST incluir al menos una tecla modificadora. Si la combinación no se puede registrar (la usa otra app o el sistema), la app MUST avisarlo y conservar el atajo anterior. El atajo SHALL guardarse entre reinicios y poder volver al predeterminado.

#### Scenario: Cambiar el atajo
- **WHEN** el usuario abre Preferencias, presiona "Cambiar" y luego ⌃⌥Espacio
- **THEN** el atajo queda en ⌃⌥Espacio de inmediato, el anterior deja de funcionar y el nuevo sigue después de reiniciar

#### Scenario: Atajo ocupado
- **WHEN** el usuario elige una combinación que otra app ya tiene registrada
- **THEN** Preferencias indica que no se pudo usar y el atajo anterior sigue funcionando

#### Scenario: Combinación sin modificador
- **WHEN** el usuario presiona solo una letra
- **THEN** Preferencias la rechaza y pide incluir ⌘, ⌥, ⌃ o ⇧

### Requirement: La página no controla la Mac
La interfaz mostrada en la app se carga desde el gateway, y la app MUST NOT exponerle ninguna API nativa (archivos, comandos, ventanas, preferencias). El control del overlay lo hace solo la parte nativa de la app; las preferencias solo se cambian desde la ventana de Preferencias, que es contenido local de la app.

#### Scenario: Contenido remoto
- **WHEN** la página del gateway intenta usar una API nativa de la app
- **THEN** la llamada no está disponible y no tiene ningún efecto en la Mac

### Requirement: Sin conexión con el servidor
Si el gateway no responde, la app SHALL seguir en reposo invisible, indicarlo en el ícono de la barra de menú y reconectarse sola cuando vuelva.

#### Scenario: Servidor reiniciándose
- **WHEN** el gateway se reinicia mientras la app está abierta
- **THEN** el ícono indica "sin conexión" y, al volver el gateway, la app se reconecta sin intervención del usuario
