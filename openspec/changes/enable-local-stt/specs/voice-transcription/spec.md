# Spec Delta

## Purpose

Permite que Finnip entienda las notas de voz que recibe, transcribiéndolas localmente en el servidor, sin depender de servicios externos ni perder la capacidad al reiniciar, recrear o actualizar Hermes.

## ADDED Requirements

### Requirement: Transcripción local de notas de voz
Cuando el usuario envía una nota de voz por Telegram, Finnip SHALL transcribirla en el servidor, sin enviar el audio a un servicio externo, y responder al contenido transcrito.

#### Scenario: Nota de voz en español
- **WHEN** el usuario manda una nota de voz que dice "¿qué hora es?"
- **THEN** Finnip responde a esa pregunta
- **AND** los logs de Hermes no registran `Voice transcription failed`

### Requirement: Idioma de transcripción
La transcripción SHALL usar español como idioma por defecto.

#### Scenario: Transcripción en español
- **WHEN** se transcribe una nota de voz en español
- **THEN** el texto resultante está en español y no traducido al inglés

### Requirement: Permanencia ante reinicio, recreación y actualización
La capacidad de transcribir SHALL mantenerse después de reiniciar el contenedor de Hermes, de recrearlo o de actualizarlo a una imagen más reciente, sin reinstalar nada a mano.

#### Scenario: Contenedor reiniciado
- **WHEN** se ejecuta `docker compose restart hermes`
- **THEN** la siguiente nota de voz se transcribe

#### Scenario: Contenedor recreado
- **WHEN** el contenedor se recrea con `docker compose up -d --force-recreate hermes`
- **THEN** la siguiente nota de voz se transcribe sin instalar nada a mano

### Requirement: Conservación de los datos de Finnip
Habilitar la transcripción SHALL conservar la memoria, la personalidad, la configuración, los plugins y las sesiones de Finnip.

#### Scenario: Arranque tras habilitar el STT
- **WHEN** Hermes arranca por primera vez con el STT local habilitado
- **THEN** Finnip conserva su memoria, su `SOUL.md`, sus plugins (`finnip-lights`, `finnip-voice`) y su conexión con Telegram
