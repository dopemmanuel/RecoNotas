# Respuestas a Preguntas sobre el bot RecoNotas


## Gestión de Datos

**¿Cómo se gestionan los datos desde su generación hasta su eliminación?**  
Los datos se generan cuando TU como usuario crea notas o recordatorios y se almacenan en una base de datos SQLite(que es similar en colsultas a oracle). Se eliminan manualmente con comandos como `/deletenote` o automáticamente al enviar recordatorios.

**¿Qué estrategia sigues para garantizar la consistencia e integridad de los datos?**  
Uso transacciones SQL para evitar corrupción de datos y validaciones para prevenir errores como inyecciones SQL(La IA me recomendo usar el SQLite para evitar errores, tambien porque es mas ligero).

**Si no trabajas con datos, ¿cómo podrías incluir una funcionalidad que los gestione?**  
Podría permitir a los usuarios guardar enlaces, archivos o tareas en una base de datos local o en la nube.

---

## Almacenamiento en la Nube

**Si tu software utiliza almacenamiento en la nube, ¿cómo garantizas la seguridad y disponibilidad?**  
Actualmente no uso la nube, pense sincronizarlo con google calendar pero se me dificulto por lo de la API.

**¿Qué alternativas consideraste y por qué elegiste tu solución actual?**  
Consideré Firebase, PostgresSQL o OracleSQL(que use el año pasado), pero elegí SQLite poque la IA recomendo que es el menos propenso a errores, es mas fleizbble y por su simplicidad.

**Si no usas la nube, ¿cómo podrías integrarla en futuras versiones?**  
Podría integrar la nube para sincronizar datos entre dispositivos usando cuentas de Google... No prometo nada😅.

---

## Seguridad y Regulación

**¿Qué medidas de seguridad implementaste?**  
Uso una base de datos local (SQLite) y valido entradas para evitar inyecciones SQL. También limito el acceso a los datos por usuario.

**¿Qué normativas podrían afectar el uso de tu software?**  
Si el proyecto escalara, tendría que cumplir con el GDPR, implementando políticas de privacidad y cifrado de datos.

**Si no implementaste medidas de seguridad, ¿qué riesgos identificas?**  
El riesgo principal es el acceso no autorizado a la base de datos. Lo abordaría con autenticación y cifrado.

---

## Implicación de las THD en Negocio y Planta

**¿Qué impacto tendría tu software en un entorno de negocio o planta industrial?**  
Podría usarse para gestionar tareas, reuniones o mantenimientos, mejorando la organización y eficiencia.

**¿Cómo podría mejorar procesos operativos o la toma de decisiones?**  
Al organizar tareas y recordatorios, reduciría errores por olvidos y mejoraría la productividad.

**Si no aplica directamente, ¿qué otros entornos podrían beneficiarse?**  
Instituciones educativas o equipos de desarrollo de software podrían usarlo para gestionar tareas y plazos.

---

## Mejoras en IT y OT

**¿Cómo puede tu software facilitar la integración entre IT y OT?**  
Podría integrarse con sistemas IT y OT para gestionar alertas y tareas, como mantenimientos preventivos.

**¿Qué procesos podrían beneficiarse de tu solución?**  
Procesos como gestión de inventarios, mantenimiento preventivo o planificación de proyectos.

**Si no aplica a IT u OT, ¿cómo podrías adaptarlo?**  
Podría adaptarse para gestionar tareas en desarrollo de software, como recordatorios para revisar código.

---

## Tecnologías Habilitadoras Digitales (THD)

**¿Qué THD has utilizado o podrías integrar?**  
Actualmente no uso THD, pero grn parte del proyecto fue inpulsado por IA, me ayudo a para sugerir recordatorios automáticos.

**¿Cómo mejorarían estas tecnologías tu software?**  
Harían el software más proactivo y personalizado, mejorando la experiencia del usuario.

**Si no has utilizado THD, ¿cómo podrías implementarlas?**  
Podría usar IA para recomendaciones o IoT para recordar tareas relacionadas con dispositivos inteligentes.

---

# FINOO
