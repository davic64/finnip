# Spec Delta

## Purpose

Muestra en el holograma los datos de los que Finnip está hablando (servidor, agenda, clima y correo), solo mientras habla de ellos.

## ADDED Requirements

### Requirement: Panel a la par de la respuesta

Cuando la frase del usuario pide datos de un tema con panel, `voice-gateway` SHALL leer esos datos antes de llamar al modelo, SHALL enviarlos a la PWA como un evento `panel` y SHALL incluirlos en el prompt, para que la voz y el panel muestren los mismos datos.

#### Scenario: Agenda del día

- **WHEN** el usuario dice "¿qué tengo hoy en mi calendario?"
- **THEN** la PWA muestra un panel holográfico con los eventos de hoy antes de que suene la respuesta
- **AND** Finnip menciona esos mismos eventos

#### Scenario: Sin panel para otros temas

- **WHEN** el usuario dice "apaga la lámpara"
- **THEN** no aparece ningún panel

### Requirement: Panel temporal

La PWA SHALL ocultar el panel cuando Finnip termine de hablar o el usuario lo interrumpa, y el holograma SHALL volver a su tamaño normal.

#### Scenario: Fin de la respuesta

- **WHEN** Finnip termina de leer el clima
- **THEN** el panel del clima desaparece en 1.5 s o menos y el holograma vuelve al centro

### Requirement: Fallo de una fuente

Si un lector de datos falla o tarda más de 1.5 s, `voice-gateway` SHALL omitir ese panel y SHALL llamar al modelo igual, sin mostrar detalles del error.

#### Scenario: Home Assistant caído

- **WHEN** el usuario pregunta por el clima y `home-bridge` no responde
- **THEN** no aparece el panel y Finnip contesta con sus propias herramientas o dice que no pudo consultarlo

### Requirement: Calendario por voz

Finnip SHALL poder consultar y crear eventos del calendario de Google del usuario a través de Home Assistant.

#### Scenario: Crear un evento

- **WHEN** el usuario dice "agenda dentista mañana a las 5 de la tarde"
- **THEN** el evento aparece en su Google Calendar y Finnip lo confirma

### Requirement: Correo de solo lectura

El panel de Gmail SHALL usar una credencial de solo lectura y SHALL mostrar solo remitente, asunto y hora, nunca el cuerpo.

#### Scenario: Correos sin leer

- **WHEN** el usuario pregunta "¿tengo correos importantes?"
- **THEN** el panel muestra hasta 5 correos no leídos de la bandeja principal, sin el cuerpo del mensaje
