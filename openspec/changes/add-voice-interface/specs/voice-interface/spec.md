# Spec Delta

## Purpose

Permite conversar por voz con Finnip desde una PWA propia, con dos modos de micrófono y respuestas habladas en streaming. Usa un protocolo de cliente que también podrá usar el dispositivo ESP32.

## ADDED Requirements

### Requirement: Modo conversación

La PWA SHALL ofrecer un modo conversación que se activa y se desactiva con un botón. Mientras está activo, el micrófono SHALL permanecer abierto y cada frase del usuario SHALL tratarse como un turno, sin pulsar nada más.

#### Scenario: Conversación de varios turnos

- **WHEN** el usuario activa el modo conversación, dice "¿qué hora es?", espera la respuesta y luego dice "apaga la lámpara"
- **THEN** Finnip responde por voz a la primera frase
- **AND** responde por voz a la segunda frase sin que el usuario toque la interfaz

#### Scenario: Sin escucha tras desactivar

- **WHEN** el usuario desactiva el modo conversación y luego habla
- **THEN** la PWA no captura audio
- **AND** el indicador de micrófono del sistema operativo está apagado
- **AND** el servidor no recibe audio de ese cliente

### Requirement: Modo un mensaje

La PWA SHALL ofrecer un modo de un solo mensaje: un toque abre el micrófono para una frase y el micrófono SHALL cerrarse solo cuando el VAD detecte el final de esa frase.

#### Scenario: Una sola frase

- **WHEN** el usuario toca el botón de un mensaje y dice "prende las luces"
- **THEN** el micrófono se cierra al terminar la frase
- **AND** Finnip ejecuta la orden y responde por voz
- **AND** una segunda frase dicha después no se captura

### Requirement: Interrumpir a Finnip

El usuario SHALL poder interrumpir a Finnip mientras habla, con un toque en cualquier modo o con la voz en modo conversación. Al interrumpirlo, Finnip SHALL callarse de inmediato y el turno en curso SHALL cancelarse en el servidor.

#### Scenario: Interrumpir con un toque

- **WHEN** Finnip está respondiendo y el usuario toca el botón
- **THEN** el audio se detiene en 200 ms o menos
- **AND** el servidor deja de generar y enviar esa respuesta

#### Scenario: Interrumpir con la voz

- **WHEN** Finnip está respondiendo en modo conversación y el usuario dice "no, espera, mejor apaga la lámpara"
- **THEN** Finnip se calla
- **AND** procesa la nueva frase como un turno normal y responde a ella

#### Scenario: Interrupción por voz desactivada

- **WHEN** el usuario desactiva "Interrumpir con la voz" y habla mientras Finnip responde
- **THEN** Finnip sigue hablando
- **AND** el toque sigue interrumpiéndolo

### Requirement: Finnip no se interrumpe a sí mismo

La voz de Finnip captada por el micrófono SHALL NOT interrumpir su propia respuesta ni crear un turno nuevo.

#### Scenario: Respuesta por altavoz

- **WHEN** Finnip responde por el altavoz de la Mac con el modo conversación activo y nadie más habla
- **THEN** la respuesta se reproduce completa
- **AND** no se crea ningún turno nuevo con el audio de esa respuesta

### Requirement: Contexto de lo que se alcanzó a oír

Tras una interrupción, Finnip SHALL saber qué parte de su respuesta alcanzó a oír el usuario y SHALL NOT dar por dicha la parte que no sonó.

#### Scenario: Respuesta cortada a la mitad

- **WHEN** Finnip empieza a enumerar tres pendientes, el usuario lo interrumpe tras el primero y pregunta "¿cuál era el segundo?"
- **THEN** Finnip responde con el segundo pendiente, sin asumir que ya lo había dicho

### Requirement: Respuesta hablada en streaming

El servidor SHALL sintetizar y enviar la respuesta frase por frase, y el cliente SHALL empezar a reproducir la primera frase antes de que termine de generarse la respuesta completa.

#### Scenario: Primer audio rápido

- **WHEN** el usuario termina de decir una pregunta corta que no usa herramientas
- **THEN** el primer audio de respuesta empieza a sonar en 3 segundos o menos, medido en la red local por Tailscale

#### Scenario: Reproducción continua

- **WHEN** la respuesta tiene varias frases
- **THEN** el cliente las reproduce en orden y sin cortes audibles entre frases

### Requirement: Órdenes de luces inmediatas

Una orden simple de encender o apagar dicha en la PWA SHALL ejecutarse por el atajo `finnip-lights` antes de la respuesta del modelo, igual que en Telegram.

#### Scenario: Apagar todas las luces

- **WHEN** el usuario dice "apaga todas las luces"
- **THEN** las luces se apagan en 2 segundos o menos desde el final de la frase
- **AND** Finnip confirma por voz después

### Requirement: Protocolo de cliente compartido

El servidor SHALL exponer un único WebSocket `/ws` con el protocolo documentado en design.md. Cualquier cliente que lo implemente, incluido un ESP32, SHALL poder conversar con Finnip sin la PWA.

#### Scenario: Cliente sin navegador

- **WHEN** un script de prueba envía `hello`, frames PCM16 de 16 kHz con una frase grabada y `utterance_end`
- **THEN** recibe `transcript`, uno o más pares `audio`/frames binarios y `done`

#### Scenario: Cancelar un turno

- **WHEN** el cliente envía `cancel` mientras Finnip responde
- **THEN** el servidor deja de enviar audio de ese turno y envía `done`

### Requirement: Acceso restringido a Tailscale

El servicio SHALL ser accesible solo por Tailscale con HTTPS, y SHALL rechazar a cualquier usuario que no esté en `ALLOWED_TAILSCALE_USERS`. La clave del API server de Hermes SHALL permanecer solo en el servidor.

#### Scenario: Usuario no permitido

- **WHEN** un dispositivo de la tailnet con un usuario no listado abre la PWA
- **THEN** el servidor responde 403 y no abre el WebSocket

#### Scenario: Fuera de la tailnet

- **WHEN** alguien intenta conectarse desde internet sin Tailscale
- **THEN** no hay ningún puerto del servicio alcanzable

#### Scenario: Clave protegida

- **WHEN** se inspecciona el código y el tráfico de la PWA
- **THEN** no aparece `API_SERVER_KEY` ni ningún otro token del servidor
