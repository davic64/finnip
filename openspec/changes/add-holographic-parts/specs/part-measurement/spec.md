# Spec Delta

## Purpose

Diseñar piezas que encajen con objetos reales, usando las medidas más confiables disponibles, y comprobar el ajuste antes de la impresión completa.

## ADDED Requirements

### Requirement: Foto a petición del usuario
Finnip SHALL tomar una foto con la cámara de la Mac solo cuando el usuario lo pide, y SHALL dársela al modelo como imagen.

#### Scenario: Mirar un objeto
- **WHEN** el usuario dice "mira esto" con una Raspberry Pi frente a la cámara
- **THEN** Finnip identifica el objeto y lo nombra

#### Scenario: Sin app de escritorio
- **WHEN** el usuario pide una foto y la app de escritorio no está conectada
- **THEN** Finnip responde que no puede tomarla

### Requirement: Origen de las medidas
Finnip SHALL preferir las medidas oficiales del objeto identificado o las que dicta el usuario. Una medida estimada con la cámara y una referencia (tarjeta de crédito de 85.60 × 53.98 mm) SHALL presentarse como aproximada, y Finnip SHALL pedir confirmar las medidas de las que depende el ajuste.

#### Scenario: Objeto conocido
- **WHEN** la foto muestra una Raspberry Pi 4
- **THEN** Finnip usa las medidas oficiales de la placa y lo dice

#### Scenario: Estimación con tarjeta
- **WHEN** el objeto no es identificable y hay una tarjeta en la foto
- **THEN** Finnip da medidas marcadas como aproximadas y pide confirmar las críticas

### Requirement: Holgura y prueba de ajuste
Una pieza que debe encajar con otra SHALL llevar holgura (0.5 mm por defecto, o la que pida el usuario), y Finnip SHALL ofrecer imprimir primero una prueba de ajuste de la parte crítica.

#### Scenario: Funda para un objeto
- **WHEN** el usuario pide una funda para un objeto de 30 mm de ancho
- **THEN** la cavidad mide 31 mm (0.5 mm por lado) y Finnip ofrece una prueba de ajuste
