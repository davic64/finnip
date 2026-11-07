# Spec Delta

## Purpose

Permite que Finnip conteste con su propia voz en Telegram, sintetizando sus respuestas con Fish Audio y entregándolas como notas de voz, sin perder la respuesta en texto.

## ADDED Requirements

### Requirement: Respuesta hablada a notas de voz
Cuando el usuario envía una nota de voz por Telegram y el chat no tiene un modo de voz explícito, Finnip SHALL responder con el texto de siempre y además con una nota de voz que diga esa misma respuesta.

#### Scenario: Nota de voz entrante
- **WHEN** el usuario manda una nota de voz "apaga mi lámpara" en un chat sin modo `/voice` configurado
- **THEN** Finnip envía su respuesta en texto
- **AND** envía una nota de voz con el mismo contenido

#### Scenario: Mensaje de texto entrante
- **WHEN** el usuario escribe un mensaje de texto en un chat sin modo `/voice` configurado
- **THEN** Finnip responde solo con texto

### Requirement: Control del modo de voz por chat
El usuario SHALL poder elegir por chat si Finnip habla siempre, solo ante notas de voz, o nunca, y la elección SHALL persistir tras reiniciar Hermes.

#### Scenario: Voz en todas las respuestas
- **WHEN** el usuario envía `/voice tts` y después un mensaje de texto
- **THEN** Finnip responde con texto y con nota de voz

#### Scenario: Voz desactivada
- **WHEN** el usuario envía `/voice off` y después una nota de voz
- **THEN** Finnip responde solo con texto

### Requirement: Voz de Finnip
Las respuestas habladas SHALL usar la voz de Fish Audio `ae74d1059517440aa6e5d2d50598d179` y el modelo gratuito `s2.1-pro-free`, salvo que la configuración indique otra voz o modelo.

#### Scenario: Voz por defecto
- **WHEN** la configuración no define `tts.voice` ni `tts.model`
- **THEN** la síntesis usa la voz `ae74d1059517440aa6e5d2d50598d179` con el modelo `s2.1-pro-free`

#### Scenario: Voz configurada
- **WHEN** `tts.voice` define otro `reference_id`
- **THEN** la síntesis usa ese `reference_id`

### Requirement: Formato de nota de voz
El audio entregado en Telegram SHALL ser Ogg/Opus para que se muestre como burbuja de nota de voz y no como archivo adjunto.

#### Scenario: Entrega como burbuja
- **WHEN** Finnip envía una respuesta hablada en Telegram
- **THEN** Telegram la muestra como nota de voz reproducible con duración mayor a cero

### Requirement: Protección de la API key
La credencial de Fish Audio SHALL leerse solo de la variable de entorno `FISH_API_KEY` y nunca SHALL aparecer en logs, mensajes de error ni resultados visibles para el modelo o el usuario.

#### Scenario: Error de la API
- **WHEN** Fish Audio responde con un error HTTP
- **THEN** el error reportado incluye el código HTTP y un detalle breve
- **AND** no incluye la API key ni el encabezado `Authorization`

#### Scenario: Falta la API key
- **WHEN** `FISH_API_KEY` no está definida
- **THEN** la síntesis falla con un mensaje que indica que falta la variable, sin llamar a Fish Audio

### Requirement: Degradación sin voz
Si la síntesis falla o tarda demasiado, Finnip SHALL entregar igualmente la respuesta en texto.

#### Scenario: Fish Audio no disponible
- **WHEN** la llamada a Fish Audio falla por red, error HTTP o tiempo de espera agotado
- **THEN** el usuario recibe la respuesta en texto
- **AND** no recibe una nota de voz vacía ni corrupta
