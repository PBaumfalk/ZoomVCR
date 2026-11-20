# 16 – Bekannte Einschränkungen

- **Eine Aufnahme gleichzeitig.** Es gibt einen Zoom-Desktop. Überschneidende Termine laufen nacheinander; die zweite Aufnahme beginnt also verspätet.
- **Nur Zoom.** Teams, Webex oder Browser-Konferenzen werden nicht unterstützt.
- **Zoom-Oberfläche per Texterkennung.** Zoom bietet für den Linux-Client keine Steuerschnittstelle. Erkennung von Warteraum, Namen und Ton-Dialogen ist Heuristik; neue Zoom-Versionen können Anpassungen erfordern. Bei Zweifel wartet ZoomVCR auf eine Bestätigung statt zu raten.
- **Name in Zoom.** Der Name wird über einen inoffiziellen Parameter übergeben und danach geprüft. Was andere Teilnehmer tatsächlich gesehen haben, lässt sich nicht belegen.
- **Keine Teilnahmebestätigung.** ZoomVCR beantwortet keine Umfragen, Anwesenheitsabfragen oder Fragen des Referenten.
- **Kein Umgehen von Sperren.** Aufnahmesperren, Anmeldungen, Warteräume und Kennwortabfragen werden respektiert. Kennwortabfragen ohne `pwd` im Link sind per VNC zu beantworten.
- **Alle sehen alles.** Rechte gelten für die ganze Mediathek, nicht je Aufnahme. Keine Freigaben einzelner Aufnahmen an einzelne Personen.
- **Schnitt nur nach Ton.** Ein Standbild mit Hintergrundmusik bleibt drin; eine stille Folie mit Text wird nach zwei Minuten herausgeschnitten.
- **KI-Auswertung ohne Gewähr.** Transkription und Auswertung können Paragraphen, Aktenzeichen und Namen falsch verstehen. Rechtsquellen sind ungeprüfte Funde.
- **Kein automatisches Löschen.** Aufbewahrungsfristen setzt der Betreiber von Hand um.
- **Auditprotokoll** ist eine Datenbanktabelle, nicht manipulationssicher.
- **x86-64 only** wegen des Zoom-Linux-Clients.
