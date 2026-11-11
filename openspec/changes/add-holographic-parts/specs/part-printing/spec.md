# Spec Delta

## Purpose

Imprimir una pieza diseñada en el Ender-3 V3 SE por voz, sin pasos manuales en el rebanador ni en OctoPrint, y sin imprimir nunca sin la confirmación del usuario.

## ADDED Requirements

### Requirement: Rebanar una pieza
El servicio de piezas SHALL rebanar una versión con CuraEngine, la máquina `creality_ender3v3se` y los valores por defecto de Cura, con el perfil de material y calidad de Cura del material de la pieza (PLA por defecto, o PETG), y SHALL devolver el tiempo y el filamento estimados.

#### Scenario: Pieza en PETG
- **WHEN** el usuario dice "esta pieza va en PETG"
- **THEN** el G-code usa las temperaturas y la calidad de PETG de Cura, y Finnip menciona el material al confirmar

#### Scenario: Sin material indicado
- **WHEN** el usuario no dice el material
- **THEN** la pieza se rebana en PLA

#### Scenario: Estimar
- **WHEN** el usuario dice "¿cuánto tardaría en imprimirse?"
- **THEN** Finnip responde con el tiempo y los gramos estimados de la versión actual

### Requirement: Ajustes de impresión por pieza
Cuando el usuario pide ajustes para una pieza, Finnip SHALL guardarlos con esa versión y usarlos al rebanar. El servicio SHALL aceptar solo claves y valores válidos según las definiciones de Cura, y SHALL devolver los ajustes que difieren de la base.

#### Scenario: Relleno y soportes
- **WHEN** el usuario dice "imprímela con relleno al 40 % y soportes"
- **THEN** el G-code usa `infill_sparse_density=40` y soportes, y Finnip menciona esos ajustes al confirmar

#### Scenario: Ajuste inexistente
- **WHEN** llega un ajuste con una clave que Cura no conoce
- **THEN** el servicio lo rechaza sin rebanar

### Requirement: Imprimir con confirmación
Antes de imprimir, Finnip SHALL decir el nombre de la pieza, el tiempo y el filamento, y SHALL preguntar si la cama está libre. El plugin SHALL rechazar la impresión sin `confirmed: true`, sin una versión rebanada, o con la impresora ocupada o desconectada.

#### Scenario: Imprimir
- **WHEN** el usuario dice "imprímela" y confirma que la cama está libre
- **THEN** el G-code se sube a OctoPrint y empieza la impresión

#### Scenario: Impresora ocupada
- **WHEN** el usuario pide imprimir mientras otra impresión está en curso
- **THEN** Finnip responde que la impresora está ocupada y no envía nada a OctoPrint

### Requirement: Seguimiento con el plugin de la impresora
Una impresión iniciada por Finnip SHALL seguirse con los avisos del plugin `finnip-printer`.

#### Scenario: Fin de la impresión
- **WHEN** termina la impresión
- **THEN** Finnip lo anuncia como cualquier otra impresión
