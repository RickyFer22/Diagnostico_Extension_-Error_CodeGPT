import os
import sys
import subprocess
import re
import logging
import socket
import urllib.request
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPlainTextEdit, QPushButton, QVBoxLayout, QHBoxLayout,
    QWidget, QProgressBar, QMenuBar, QAction, QMessageBox, QFileDialog, QLabel,
    QCheckBox, QToolTip
)
from PyQt5.QtGui import QFont, QCursor, QColor, QIcon
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QUrl
from PyQt5.QtWebEngineWidgets import QWebEngineView

# Configuración del registro de logs
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='troubleshooter.log'
)
logger = logging.getLogger(__name__)

class WorkerThread(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__()
        self.parent = parent

    def run(self):
        issues = []
        try:
            # Verificar la extensión CodeGPT
            ext_id = self.find_codegpt_extension_id()
            if ext_id:
                logger.info(f"Extensión CodeGPT encontrada: {ext_id}")
                result, ext_issues = self.parent.check_vscode_extensions(ext_id)
            else:
                logger.warning("Extensión CodeGPT no encontrada")
                result = "❌ No se pudo encontrar la extensión CodeGPT\n"
                ext_issues = ["Extensión CodeGPT no instalada"]
            self.progress.emit(result)
            issues.extend(ext_issues)
        except Exception as e:
            logger.error(f"Error al verificar extensiones: {str(e)}", exc_info=True)
            self.error.emit(f"Error al verificar extensiones: {str(e)}")
            issues.append(f"Error al verificar extensiones: {str(e)}")

        # Verificar conectividad de red
        try:
            result, net_issues = self.check_network_connectivity()
            self.progress.emit(result)
            issues.extend(net_issues)
        except Exception as e:
            logger.error(f"Error al verificar la red: {str(e)}", exc_info=True)
            self.error.emit(f"Error al verificar la red: {str(e)}")
            issues.append(f"Error al verificar la red: {str(e)}")

        self.finished.emit(issues)

    def find_codegpt_extension_id(self):
        """
        Busca el ID de la extensión CodeGPT en las extensiones instaladas.
        """
        try:
            result = subprocess.run(['code', '--list-extensions', '--show-versions'],
                                    capture_output=True, text=True, shell=True)
            extensions = result.stdout.splitlines()
            for ext in extensions:
                if 'codegpt' in ext.lower():
                    return ext.split('@')[0]  # Retorna el ID sin la versión
            return None
        except Exception as e:
            logger.error(f"Error al buscar el ID de la extensión CodeGPT: {str(e)}", exc_info=True)
            return None

    def check_network_connectivity(self):
        """
        Verifica la conectividad de red con los dominios de CodeGPT.
        """
        results = []
        issues = []

        # Dominios de CodeGPT
        codegpt_domains = ['api.codegpt.co', 'storage.codegpt.co', 'api.github.com', 'github.com']

        # Verificar resolución DNS
        for domain in codegpt_domains:
            try:
                socket.gethostbyname(domain)
                results.append(f"✅ Resolución DNS exitosa para {domain}")
            except socket.gaierror:
                msg = f"❌ Resolución DNS fallida para {domain}"
                results.append(msg)
                issues.append(f"Problema de DNS con {domain}")

        # Verificar conectividad HTTP
        for domain in codegpt_domains:
            try:
                urllib.request.urlopen(f"https://{domain}", timeout=5)
                results.append(f"✅ Conexión HTTP exitosa a {domain}")
            except Exception as e:
                if "403" not in str(e):  # Ignorar errores 403
                    msg = f"❌ Conexión HTTP fallida a {domain}: {str(e)}"
                    results.append(msg)
                    issues.append(f"Problema de conectividad HTTP con {domain}")

        # Verificar dominios de referencia
        reference_domains = ['google.com', 'microsoft.com']
        for domain in reference_domains:
            try:
                urllib.request.urlopen(f"https://{domain}", timeout=5)
                results.append(f"✅ Conexión a {domain} exitosa (prueba de referencia)")
            except Exception as e:
                msg = f"❌ Conexión a {domain} fallida: posible problema general de red"
                results.append(msg)
                issues.append("Problemas generales de conectividad de red detectados")

        return "\n".join(results) + "\n", issues


class FixWorker(QThread):
    progress = pyqtSignal(str)
    error = pyqtSignal(str)
    finished = pyqtSignal()
    MAX_RETRIES = 3

    def __init__(self, issues, parent=None):
        super().__init__()
        self.issues = issues
        self.parent = parent

    def run(self):
      """
      Ejecuta las soluciones basadas en los problemas detectados.
      """
      for issue in self.issues:
            retry_count = 0
            while retry_count < self.MAX_RETRIES:
                try:
                    if "DNS resolution issue" in issue:
                       self.fix_dns_issues()
                    elif "HTTP connectivity issue" in issue:
                        self.fix_network_issues()
                    elif "General network connectivity issues" in issue:
                        self.fix_general_network()
                    break  # If successful, exit loop
                except Exception as e:
                    retry_count += 1
                    if retry_count < self.MAX_RETRIES:
                        self.progress.emit(f"Reintentando operación ({retry_count}/{self.MAX_RETRIES})...")
                    else:
                        logger.error(f"Error después de {self.MAX_RETRIES} intentos: {str(e)}", exc_info=True)
                        self.error.emit(f"Error después de {self.MAX_RETRIES} intentos: {str(e)}")
                        break # Exit loop after max retries
      self.finished.emit()

    def fix_dns_issues(self):
        """
        Intenta resolver problemas de DNS.
        """
        self.progress.emit("Limpiando caché DNS...")
        try:
            subprocess.run(['ipconfig', '/flushdns'], check=True, shell=True)
            self.progress.emit("✅ Caché DNS limpiada exitosamente\n")
        except subprocess.CalledProcessError as e:
            raise Exception(f"Error al limpiar la caché DNS: {str(e)}")

    def fix_network_issues(self):
      """
      Intenta resolver problemas de red.
      """
      self.progress.emit("Reconfigurando adaptador de red...\n")
      try:
           # Try disabling and then enabling network adapter
          adapter_name = self.get_first_network_adapter_name()
          if adapter_name:
             self.progress.emit(f"Deshabilitando adaptador de red '{adapter_name}'...\n")
             subprocess.run(['netsh', 'interface', 'set', 'interface', f'name="{adapter_name}"', 'admin=disabled'],
                             check=True, shell=True)
             self.progress.emit(f"Habilitando adaptador de red '{adapter_name}'...\n")
             subprocess.run(['netsh', 'interface', 'set', 'interface', f'name="{adapter_name}"', 'admin=enabled'],
                              check=True, shell=True)
             self.progress.emit("✅ Adaptador de red reconfigurado.\n")
          else:
              self.progress.emit("⚠️ No se detectó un adaptador de red activo para reconfigurar.\n")
      except subprocess.CalledProcessError as e:
             raise Exception(f"Error al reconfigurar el adaptador de red: {str(e)}")

    def fix_general_network(self):
       """
       Intenta resolver problemas generales de red.
       """
       self.progress.emit("Restableciendo la configuración de red...\n")
       try:
           subprocess.run(['netsh', 'int', 'ip', 'reset'], check=True, shell=True)
           subprocess.run(['netsh', 'winsock', 'reset'], check=True, shell=True)
           self.progress.emit("✅ Configuración de red restablecida.\n")
           self.fix_network_issues()  # Reconfigurar el adaptador de red
       except Exception as e:
            raise Exception(f"Error al restablecer la configuración de red: {str(e)}")


    def get_first_network_adapter_name(self):
      """
      Obtiene el nombre del primer adaptador de red habilitado que no sea virtual.
      """
      try:
          result = subprocess.run(['netsh', 'interface', 'show', 'interface'],
                                  capture_output=True, text=True, shell=True)
          lines = result.stdout.splitlines()
          for line in lines:
              match = re.search(r'([^ ]+)(?=\s+Enabled)', line)
              if match:
                  adapter_name = match.group(1).strip()
                  if 'Virtual' not in adapter_name:
                      return adapter_name
          return None
      except Exception as e:
          logger.error(f"Error al obtener el nombre del adaptador: {str(e)}", exc_info=True)
          return None

class CodeGPTTroubleshooter(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Diagnóstico de la Extensión CodeGPT")
        self.setGeometry(100, 100, 800, 600)
        self.setup_ui()
        self.setup_styles()
        self.setup_tooltips()

    def setup_ui(self):
        """
        Configura la interfaz de usuario.
        """
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout()

        # Enlace "REPORT A BUG"
        self.bug_report_label = QLabel('<a href="https://github.com/JudiniLabs/code-gpt-docs/issues">REPORT A BUG</a>', self)
        self.bug_report_label.setAlignment(Qt.AlignRight | Qt.AlignTop)
        self.bug_report_label.setOpenExternalLinks(True)
        self.bug_report_label.setStyleSheet("color: red; font-weight: bold;")
        main_layout.addWidget(self.bug_report_label)

        # Mensaje de reinicio
        self.restart_message = QLabel("¿HAS PROBADO CON REINICIAR TU PC? 😉", self)
        self.restart_message.setFont(QFont("Arial", 16, QFont.Bold))
        self.restart_message.setStyleSheet("color: black; font-style: italic;")
        self.restart_message.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.restart_message)

        # Barra de menú
        self.menu_bar = QMenuBar()
        self.file_menu = self.menu_bar.addMenu("Archivo")
        self.save_action = QAction("Guardar Informe", self)
        self.save_action.triggered.connect(self.save_report)
        self.file_menu.addAction(self.save_action)
        self.exit_action = QAction("Salir", self)
        self.exit_action.triggered.connect(self.close)
        self.file_menu.addAction(self.exit_action)
        self.setMenuBar(self.menu_bar)

        # Etiqueta de título
        self.title_label = QLabel("Diagnóstico de Extensión CodeGPT", self)
        self.title_label.setFont(QFont("Arial", 18, QFont.Bold))
        self.title_label.setStyleSheet("color: #00AA00; text-align: center;")
        main_layout.addWidget(self.title_label, alignment=Qt.AlignCenter)

        # Checkbox de modo detallado
        self.verbose_checkbox = QCheckBox("Modo Detallado", self)
        self.verbose_checkbox.setChecked(True)
        main_layout.addWidget(self.verbose_checkbox, alignment=Qt.AlignCenter)

        # Área de texto para resultados
        self.result_text = QPlainTextEdit(self)
        font = QFont("Courier", 12)
        self.result_text.setFont(font)
        self.result_text.setReadOnly(True)
        main_layout.addWidget(self.result_text)

        # Barra de progreso
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # Layout de botones
        button_layout = QHBoxLayout()

        # Botón de ejecutar diagnósticos
        self.run_button = QPushButton("Ejecutar Diagnósticos", self)
        self.run_button.clicked.connect(self.run_diagnostics_threaded)
        button_layout.addWidget(self.run_button)

        # Botón de solucionar problemas
        self.fix_button = QPushButton("Intentar Solucionar Problemas", self)
        self.fix_button.clicked.connect(self.fix_issues)
        button_layout.addWidget(self.fix_button)

        # Botón de reiniciar extensión
        self.restart_extension_button = QPushButton("Reiniciar Extensión", self)
        self.restart_extension_button.clicked.connect(self.restart_extension)
        button_layout.addWidget(self.restart_extension_button)

        # Botón de reiniciar PC (color rojo, a la derecha)
        self.restart_pc_button = QPushButton("Reiniciar PC", self)
        self.restart_pc_button.clicked.connect(self.restart_pc)
        self.restart_pc_button.setStyleSheet("background-color: red; color: white;")
        button_layout.addWidget(self.restart_pc_button)

        # Aplicar fuente a los botones
        font = QFont()
        font.setPointSize(12)
        self.run_button.setFont(font)
        self.fix_button.setFont(font)
        self.restart_extension_button.setFont(font)
        self.restart_pc_button.setFont(font)

        main_layout.addLayout(button_layout)

        # Etiqueta de estado
        self.status_label = QLabel(self)
        self.status_label.setStyleSheet("color: #00AA00;")
        main_layout.addWidget(self.status_label, alignment=Qt.AlignCenter)

        # Establecer el layout principal
        self.central_widget.setLayout(main_layout)

        # Inicializar workers
        self.worker = None
        self.fix_worker = None

    def setup_styles(self):
        """
        Configura los estilos de la interfaz.
        """
        button_style = """
        QPushButton {
            background-color: #4CAF50;
            border: none;
            color: white;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #45a049;
        }
        QPushButton:pressed {
            background-color: #357a38;
        }
        """
        self.run_button.setStyleSheet(button_style)
        self.fix_button.setStyleSheet(button_style)
        self.restart_extension_button.setStyleSheet(button_style)
        self.restart_pc_button.setStyleSheet(button_style + "background-color: red;")

    def setup_tooltips(self):
        """
        Configura los tooltips para los elementos de la interfaz.
        """
        self.run_button.setToolTip("Ejecuta un diagnóstico completo del sistema")
        self.fix_button.setToolTip("Intenta resolver automáticamente los problemas detectados")
        self.restart_pc_button.setToolTip("Reinicia la PC para aplicar todos los cambios")
        self.restart_extension_button.setToolTip("Reinicia la extensión CodeGPT")
        self.verbose_checkbox.setToolTip("Muestra información detallada del diagnóstico")

    def show_error(self, message):
        """
        Muestra un diálogo de error.
        """
        QMessageBox.critical(self, "Error", message)
        logger.error(message)

    def check_vscode_extensions(self, ext_id):
        """
        Verifica si la extensión CodeGPT está instalada.
        """
        result = subprocess.run(['code', '--list-extensions', '--show-versions'],
                                capture_output=True, text=True, shell=True)
        extensions = result.stdout.splitlines()
        codegpt_extensions = [ext for ext in extensions if ext_id in ext]
        if codegpt_extensions:
            res = "✅ Extensiones de CodeGPT Instaladas:\n"
            for ext in codegpt_extensions:
                res += f"   - {ext}\n"
            return res, []
        else:
            res = "❌ No se encontraron extensiones de CodeGPT\n"
            return res, ["Extensión de CodeGPT no instalada"]

    def run_diagnostics_threaded(self):
        """
        Inicia el diagnóstico en un hilo separado.
        """
        self.progress_bar.setVisible(True)
        self.status_label.setText("Ejecutando diagnósticos...")
        self.worker = WorkerThread(parent=self)
        self.worker.progress.connect(self.append_result)
        self.worker.finished.connect(self.on_diagnostics_finished)
        self.worker.error.connect(self.show_error)
        self.worker.start()

    def append_result(self, text):
        """
        Añade texto al área de resultados.
        """
        self.result_text.appendPlainText(text)
        if self.verbose_checkbox.isChecked():
            logger.debug(text)

    def on_diagnostics_finished(self, issues):
        """
        Maneja la finalización del diagnóstico.
        """
        self.progress_bar.setVisible(False)
        self.status_label.setText("Diagnóstico completado")
        self.issues = issues
        self.generate_report()

    def generate_report(self):
        """
        Genera el informe de diagnóstico.
        """
        self.result_text.appendPlainText("\n🔍 Informe de Diagnóstico de CodeGPT:\n")
        if not self.issues:
            self.result_text.appendPlainText("✨ ¡No se detectaron problemas!\n")
        else:
            self.result_text.appendPlainText("⚠️ Problemas Detectados:\n")
            for issue in self.issues:
                self.result_text.appendPlainText(f"- {issue}\n")
            self.result_text.appendPlainText("\n💡 Acciones Recomendadas:\n")
            self.result_text.appendPlainText("1. Reiniciar VSCode\n")
            self.result_text.appendPlainText("2. Verificar configuración de red\n")
            self.result_text.appendPlainText("3. Limpiar caché DNS\n")
            self.result_text.appendPlainText("4. Reinstalar la extensión\n")
            self.result_text.appendPlainText("5. Reiniciar la extensión CodeGPT\n")

    def fix_issues(self):
        """
        Inicia el proceso de corrección de problemas.
        """
        if not hasattr(self, 'issues') or not self.issues:
            QMessageBox.information(self, "Información", "No hay problemas para solucionar.")
            return
        reply = QMessageBox.question(self, "Confirmar",
                                     "¿Desea intentar solucionar los problemas detectados?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.progress_bar.setVisible(True)
            self.status_label.setText("Solucionando problemas...")
            self.fix_worker = FixWorker(self.issues, parent=self)
            self.fix_worker.progress.connect(self.append_result)
            self.fix_worker.finished.connect(self.on_fix_finished)
            self.fix_worker.error.connect(self.show_error)
            self.fix_worker.start()

    def on_fix_finished(self):
        """
        Maneja la finalización del proceso de corrección.
        """
        self.progress_bar.setVisible(False)
        self.status_label.setText("Correcciones completadas")
        QMessageBox.information(self, "Información",
                                "Se han aplicado todas las correcciones posibles.\n"
                                "Se recomienda reiniciar el sistema.")

    def restart_pc(self):
        """
        Maneja el reinicio del sistema.
        """
        reply = QMessageBox.question(self, "Confirmar",
                                     "¿Está seguro de que desea reiniciar el sistema?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                subprocess.run(['shutdown', '/r', '/t', '60', '/c',
                                "El sistema se reiniciará en 60 segundos para aplicar los cambios."],
                               check=True, shell=True)
                QMessageBox.information(self, "Reinicio Programado",
                                        "El sistema se reiniciará en 60 segundos.\n"
                                        "Guarde su trabajo y cierre todos los programas.")
            except Exception as e:
                self.show_error(f"Error al reiniciar el sistema: {str(e)}")

    def restart_extension(self):
        """
        Reinicia la extensión CodeGPT.
        """
        try:
            # Ejecuta el comando para reiniciar el host de extensiones en VSCode
            subprocess.run(['code', '--command', 'workbench.action.restartExtensionHost'], check=True, shell=True)
            self.append_result("✅ Extensión CodeGPT reiniciada exitosamente.\n")
        except Exception as e:
            self.show_error(f"Error al reiniciar la extensión: {str(e)}")

    def save_report(self):
        """
        Guarda el informe en un archivo.
        """
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Guardar Informe", "", "Archivos de texto (*.txt)")
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as file:
                    file.write(self.result_text.toPlainText())
                self.status_label.setText(f"Informe guardado en {file_path}")
            except Exception as e:
                self.show_error(f"Error al guardar el informe: {str(e)}")


if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        window = CodeGPTTroubleshooter()
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        logger.critical(f"La aplicación falló: {str(e)}", exc_info=True)
        raise
