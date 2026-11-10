# Spec Delta

## Purpose

Que el usuario cree y ajuste por voz o por Telegram los modos de su casa (luces, enchufes, volumen y si llevan música), y que Finnip los active, sin editar Home Assistant a mano y sin que un modo pueda tocar nada que Finnip no controle ya.

## ADDED Requirements

### Requirement: Crear un modo
Finnip SHALL crear un modo a partir de lo que pide el usuario, como una lista ordenada de pasos. Cada paso es una acción sobre un dispositivo expuesto, de las que ese dispositivo soporta, con valores válidos. El modo queda en Home Assistant como `script.modo_<nombre>`, con el nombre "Modo <nombre>" y la etiqueta `finnip`, y MUST poder activarse de inmediato con "modo <nombre>".

#### Scenario: Modo lectura
- **WHEN** el usuario dice "crea un modo lectura: la lámpara en blanco cálido al 40 % y los monitores apagados"
- **THEN** se crea `script.modo_lectura` con esos dos pasos, y al decir "modo lectura" la lámpara y los monitores quedan así

### Requirement: Solo pasos permitidos
Un modo MUST NOT incluir dispositivos no expuestos, acciones que el dispositivo no soporta, valores fuera de rango, ni compras por Alexa. Si un paso no es válido, el modo completo MUST rechazarse sin crear ni cambiar nada, con un error que diga cuál paso falló.

#### Scenario: Dispositivo no expuesto
- **WHEN** se pide un modo que abre `lock.puerta_principal`
- **THEN** el modo se rechaza indicando el paso inválido, y Home Assistant no cambia

#### Scenario: Valor fuera de rango
- **WHEN** un paso pide brillo 150 %
- **THEN** el modo se rechaza indicando ese paso

### Requirement: Consultar y cambiar un modo
Finnip SHALL poder leer los pasos actuales de un modo y guardarlo con cambios, reemplazando sus pasos. Si el modo tiene pasos que Finnip no sabe representar (editado a mano en Home Assistant), Finnip MUST NOT sobrescribirlo y SHALL explicar que se edita en Home Assistant.

#### Scenario: Ajustar el Modo estudio
- **WHEN** el usuario dice "en el modo estudio pon la lámpara al 80 %"
- **THEN** Finnip lee los pasos del Modo estudio, cambia solo el brillo de la lámpara y guarda el resto igual

#### Scenario: Modo editado a mano
- **WHEN** un modo tiene un paso con un servicio que Finnip no maneja
- **THEN** Finnip no lo modifica y dice que ese modo se edita en Home Assistant

### Requirement: Música del modo
Cada modo SHALL indicar si lleva música elegida por Finnip. Al activar un modo con música, Finnip elige y reproduce algo acorde (con las exclusiones de gusto del usuario). Al activar un modo sin música, MUST NOT reproducir nada. Por defecto un modo nuevo lleva música, salvo que el usuario diga lo contrario.

#### Scenario: Modo sin música
- **WHEN** el usuario crea "modo siesta, sin música, todo apagado" y luego dice "modo siesta"
- **THEN** las luces se apagan y Finnip no reproduce nada

#### Scenario: Modo con música
- **WHEN** el usuario dice "modo estudio"
- **THEN** se aplican las luces y Finnip reproduce una canción o artista concreto para estudiar

### Requirement: Borrar un modo con confirmación
Finnip SHALL pedir confirmación antes de borrar un modo, nombrándolo. Solo se pueden borrar scripts `modo_*`. Cualquier otro script MUST rechazarse.

#### Scenario: Borrar el modo lectura
- **WHEN** el usuario dice "borra el modo lectura" y confirma
- **THEN** `script.modo_lectura` desaparece de Home Assistant y "modo lectura" ya no hace nada

#### Scenario: Script ajeno
- **WHEN** llega una petición para borrar `script.respaldo_nocturno`
- **THEN** Home Bridge la rechaza y el script sigue existiendo

### Requirement: Temperatura de color
Las luces que soportan temperatura de color SHALL aceptar la acción `color_temp` en Kelvin, dentro del rango que reporta la luz, tanto en órdenes directas como en pasos de un modo.

#### Scenario: Blanco cálido
- **WHEN** el usuario dice "pon la lámpara en blanco cálido"
- **THEN** la lámpara queda en una temperatura cálida (alrededor de 2700 K) y Home Bridge lo confirma con el estado que reporta Home Assistant

#### Scenario: Fuera del rango de la luz
- **WHEN** se pide 9000 K a una luz que soporta hasta 6500 K
- **THEN** la acción se rechaza con el rango permitido
