#!/usr/bin/env python3

import sys
import os
import json
import time
import threading
import multiprocessing

from PyQt5 import QtWidgets, uic
from tools.gui import *
from tools.gui.qtzeiten import QtZeiten
from tools.gui.qtkontakt import QtKontakt
from tools.its import ImpfterminService

PATH = os.path.dirname(os.path.realpath(__file__))


class HauptGUI(QtWidgets.QMainWindow):

    # Folgende Widgets stehen zur Verfügung:

    ### QLineEdit ###
    # i_kontaktdaten_pfad
    # i_zeitspanne_pfad

    ### Buttons ###
    # b_termin_suchen
    # b_code_generieren
    # b_dateien_kontaktdaten
    # b_dateien_zeitspanne
    # b_neue_kontaktdaten
    # b_neue_zeitspanne

    ### Layouts ###
    # prozesse_layout

    # TODO: Ausgabe der cmd in der GUI wiederspiegelen - wenn sowas überhaupt geht
    def __init__(self, pfad_fenster_layout: str = os.path.join(PATH, "tools/gui/main.ui")):
        """
        Main der GUI Anwendung

        Args:
            pfad_fenster_layout (str, optional): Ladet das angegebene Layout (wurde mit QT Designer erstellt https://www.qt.io/download).
            Defaults to os.path.join(PATH, "tools/gui/main.ui").
        """

        super().__init__()

        # Laden der .ui Datei und Anpassungen
        uic.loadUi(pfad_fenster_layout, self)

        # Funktionen den Buttons zuweisen
        self.b_termin_suchen.clicked.connect(self.__termin_suchen)
        self.b_code_generieren.clicked.connect(self.__code_generieren)
        self.b_dateien_kontaktdaten.clicked.connect(self.__update_kontaktdaten_pfad)
        self.b_dateien_zeitspanne.clicked.connect(self.__update_zeitspanne_pfad)
        self.b_neue_kontaktdaten.clicked.connect(lambda: self.kontaktdaten_erstellen(Modus.TERMIN_SUCHEN))
        self.b_neue_zeitspanne.clicked.connect(self.zeitspanne_erstellen)

        # Standard Pfade
        self.pfad_kontaktdaten: str = os.path.join(PATH, "data", "kontaktdaten.json")
        self.pfad_zeitspanne: str = os.path.join(PATH, "data", "zeitspanne.json")

        # Pfade in der GUI anzeigen
        self.i_kontaktdaten_pfad.setText(self.pfad_kontaktdaten)
        self.i_zeitspanne_pfad.setText(self.pfad_zeitspanne)

        # Events für Eingabefelder
        self.i_kontaktdaten_pfad.textChanged.connect(self.__update_kontaktdaten_pfad)
        self.i_zeitspanne_pfad.textChanged.connect(self.__update_zeitspanne_pfad)

        # Speichert alle termin_suchen Prozesse
        self.such_prozesse = list()

        # Überwachnung der Prozesse
        self.prozess_bewacher = threading.Thread(target=self.__check_status_der_prozesse, daemon=True)
        self.prozess_bewacher.start()

        # GUI anzeigen
        self.show()

        # Workaround, damit das Fenster hoffentlich im Vordergrund ist
        self.activateWindow()

    @staticmethod
    def start_gui():
        """
        Startet die GUI Anwendung
        """

        app = QtWidgets.QApplication(list())
        window = HauptGUI()
        app.exec_()

    def kontaktdaten_erstellen(self, modus: Modus = Modus.TERMIN_SUCHEN):
        """
        Ruft den Dialog für die Kontaktdaten auf

        Args:
            modus (Modus): Abhängig vom Modus werden nicht alle Daten benötigt. Defalut TERMIN_SUCHEN
        """

        dialog = QtKontakt(modus, self.pfad_kontaktdaten)
        dialog.show()
        dialog.exec_()

    def zeitspanne_erstellen(self):
        """
        Ruft den Dialog für die Zeitspanne auf
        """

        dialog = QtZeiten(self.pfad_zeitspanne)
        dialog.show()
        dialog.exec_()

    def __termin_suchen(self):
        """
        Startet den Prozess der terminsuche mit Impfterminservice.terminsuche in einem neuen Thread
        Dieser wird in self.such_threads hinzugefügt.
        Alle Threads sind deamon Thread (Sofort töten sobald der Bot beendet wird)
        """

        kontaktdaten = self.__get_kontaktdaten(Modus.TERMIN_SUCHEN)
        zeitspanne = self.__get_zeitspanne()

        try:
            check_alle_kontakt_daten_da(Modus.TERMIN_SUCHEN, kontaktdaten)
        except FehlendeDatenException as error:
            QtWidgets.QMessageBox.critical(self, "Daten unvollständig!", f"Es fehlen Daten in der JSON Datei\n\n{error}")
            return

        self.__start_terminsuche(kontaktdaten, zeitspanne)

    def __start_terminsuche(self, kontaktdaten: dict, zeitspanne: dict):
        """
        Startet die Terminsuche. Dies nur mit einem Thread starten, da die GUI sonst hängt

        Args:
            kontaktdaten (dict): kontakdaten aus kontaktdaten.json
            zeitspanne (dict): zeitspanne aus zeitspanne.json
        """

        kontakt = kontaktdaten["kontakt"]
        code = kontaktdaten["code"]
        plz_impfzentren = kontaktdaten["plz_impfzentren"]

        terminsuche_prozess = multiprocessing.Process(target=ImpfterminService.terminsuche, name=f"{code}-{len(self.such_prozesse)}", daemon=True, kwargs={
                                                      "code": code,
                                                      "plz_impfzentren": plz_impfzentren,
                                                      "kontakt": kontakt,
                                                      "zeitspanne": zeitspanne,
                                                      "PATH": PATH})
        try:
            terminsuche_prozess.start()
            if not terminsuche_prozess.is_alive():
                raise RuntimeError(
                    f"Terminsuche wurde gestartet, lebt aber nicht mehr!\n\nTermin mit Code: {terminsuche_prozess.getName()}\nBitte Daten Prüfen!"
                )

        except Exception as error:
            QtWidgets.QMessageBox.critical(self, "Fehler - Suche nicht gestartet!", str(error))

        else:
            QtWidgets.QMessageBox.information(self, "Suche gestartet", "Terminsuche wurde gestartet!\nWeitere Infos in der Konsole")
            self.such_prozesse.append(terminsuche_prozess)
            self.__add_prozess_in_gui(terminsuche_prozess)

    def __code_generieren(self):
        """
        Startet den Prozess der Codegenerierung
        """

        # TODO: code generierung implementieren
        QtWidgets.QMessageBox.information(self, "Noch nicht verfügbar", "Funktion nur über Konsole verfügbar")

    def __get_kontaktdaten(self, modus: Modus) -> dict:
        """
        Ladet die Kontakdaten aus dem in der GUI hinterlegten Pfad

        Args:
            modus (Modus): Abhängig vom Modus werden nicht alle Daten benötigt.

        Returns:
            dict: Kontakdaten
        """

        if not os.path.isfile(self.pfad_kontaktdaten):
            self.kontaktdaten_erstellen(modus)

        with open(self.pfad_kontaktdaten, "r", encoding='utf-8') as f:
            kontaktdaten = json.load(f)

        return kontaktdaten

    def __get_zeitspanne(self) -> dict:
        """
        Ladet die Zeitspanne aus dem in der GUI hinterlegtem Pfad

        Returns:
            dict: Zeitspanne
        """

        if not os.path.isfile(self.pfad_zeitspanne):
            self.zeitspanne_erstellen()

        with open(self.pfad_zeitspanne, "r", encoding='utf-8') as f:
            zeitspanne = json.load(f)

        # TODO: Prüfen ob Daten vollständig

        return zeitspanne

    def __update_kontaktdaten_pfad(self):
        try:
            pfad = oeffne_file_dialog_select(self, "Kontakdaten", self.pfad_kontaktdaten)
            self.pfad_kontaktdaten = pfad
        except FileNotFoundError:
            pass

    def __update_zeitspanne_pfad(self):
        try:
            pfad = oeffne_file_dialog_select(self, "Zeitspanne", self.pfad_zeitspanne)
            self.pfad_zeitspanne = pfad
        except FileNotFoundError:
            pass

    def __add_prozess_in_gui(self, prozess: multiprocessing.Process):
        """
        Die Prozesse werden in der GUI in dem prozesse_layout angezeigt
        """
        # addRow(label, field)
        label = QtWidgets.QLabel(f"Prozess: {prozess.name}")
        button = QtWidgets.QPushButton("Stoppen")
        button.setObjectName(prozess.name)
        button.clicked.connect(lambda: self.__stop_prozess(prozess))

        self.prozesse_layout.addRow(label, button)

    def __stop_prozess(self, prozess: multiprocessing.Process):
        """
        Stopped den übergebenen Prozess und löscht diesen aus der GUI

        Args:
            prozess (multiprocessing.Process): Prozess welcher getötet werden soll
        """
        prozess.kill()
        self.such_prozesse.remove(prozess)

    def __remove_prozess_von_gui(self, prozess: multiprocessing.Process):
        """
        Entfernt die Anzeige des Prozesses aus der GUI

        Args:
            prozess (multiprocessing.Process): Prozess welcher entfernt werden soll
            warnung (bool, optional): Warnung an den User ausgeben, dass der Prozess weg ist. Defaults to False.
        """

        button = self.findChild(QtWidgets.QPushButton, prozess.name)
        self.prozesse_layout.removeRow(button)

    def __check_status_der_prozesse(self):
        """
        Wird von einem Thread dauerhaft durchlaufen um zu prüfen ob ein Prozess sich beendet hat
        """

        while True:
            for prozess in self.such_prozesse:
                if not prozess.is_alive():
                    self.__remove_prozess_von_gui(prozess)
            time.sleep(5)


def main():
    """
    Startet die GUI-Anwendung
    """

    HauptGUI.start_gui()


if __name__ == "__main__":
    main()
