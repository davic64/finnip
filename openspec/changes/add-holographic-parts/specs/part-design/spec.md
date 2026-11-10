# Spec Delta

## Purpose

Permitir que el usuario describa una pieza por voz y que Finnip la genere como modelo 3D imprimible, con versiones, sin que el código generado pueda afectar al servidor.

## ADDED Requirements

### Requirement: Diseñar una pieza por voz
Finnip SHALL convertir la descripción del usuario en código OpenSCAD, y el servicio de piezas SHALL renderizarlo a STL y devolver su caja envolvente en milímetros.

#### Scenario: Soporte simple
- **WHEN** el usuario dice "hazme un soporte de 40 por 20 mm con dos agujeros de 4 mm"
- **THEN** se crea la pieza con su STL, y Finnip responde con sus medidas

#### Scenario: Código que no compila
- **WHEN** OpenSCAD devuelve un error al renderizar
- **THEN** el servicio devuelve el mensaje de error y no guarda una versión nueva

### Requirement: Versiones de una pieza
Cada cambio a una pieza SHALL crear una versión nueva y conservar las anteriores.

#### Scenario: Cambiar una medida
- **WHEN** el usuario dice "hazla 5 mm más alta"
- **THEN** existe una versión nueva con la altura cambiada y la versión anterior sigue disponible

### Requirement: Render aislado
El servicio de piezas SHALL rechazar código con `import`, `include` o `use`, y SHALL detener un render que exceda 60 segundos o su límite de memoria. El servicio no SHALL tener puertos publicados ni escribir fuera de `data/parts/`.

#### Scenario: Código que intenta leer archivos
- **WHEN** el código de una pieza contiene `import("/etc/passwd")`
- **THEN** el servicio lo rechaza sin ejecutar OpenSCAD

#### Scenario: Render demasiado largo
- **WHEN** un render tarda más de 60 segundos
- **THEN** el servicio lo detiene y responde con un error claro

### Requirement: La pieza cabe en la impresora
El servicio SHALL avisar cuando la caja envolvente de la pieza excede 220 × 220 × 250 mm.

#### Scenario: Pieza demasiado grande
- **WHEN** el usuario pide una caja de 300 mm de largo
- **THEN** Finnip avisa que no cabe en la cama de la impresora
