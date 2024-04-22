# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'rtsp_dialog.ui'
##
## Created by: Qt User Interface Compiler version 6.4.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (
    QCoreApplication,
    QDate,
    QDateTime,
    QLocale,
    QMetaObject,
    QObject,
    QPoint,
    QRect,
    QSize,
    QTime,
    QUrl,
    Qt,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QCursor,
    QFont,
    QFontDatabase,
    QGradient,
    QIcon,
    QImage,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPalette,
    QPixmap,
    QRadialGradient,
    QTransform,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QWidget,
)
import apprcc_rc


class Ui_Form(object):
    def setupUi(self, Form):
        if not Form.objectName():
            Form.setObjectName(u"Form")
        Form.resize(783, 40)
        Form.setMinimumSize(QSize(0, 40))
        Form.setMaximumSize(QSize(16777215, 41))
        icon = QIcon()
        icon.addFile(
            u":/img/icon/\u5b9e\u65f6\u89c6\u9891\u6d41\u89e3\u6790.png",
            QSize(),
            QIcon.Normal,
            QIcon.Off,
        )
        Form.setWindowIcon(icon)
        Form.setStyleSheet(u"#Form{background:rgba(120,120,120,255)}")
        self.horizontalLayout = QHBoxLayout(Form)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.horizontalLayout.setContentsMargins(-1, 5, -1, 5)
        self.label = QLabel(Form)
        self.label.setObjectName(u"label")
        self.label.setMinimumSize(QSize(0, 30))
        self.label.setMaximumSize(QSize(16777215, 30))
        self.label.setStyleSheet(
            u'QLabel{font-family: "Microsoft YaHei";\n'
            "font-size: 18px;\n"
            "font-weight: bold;\n"
            "color:white;}"
        )

        self.horizontalLayout.addWidget(self.label)

        self.rtspEdit = QLineEdit(Form)
        self.rtspEdit.setObjectName(u"rtspEdit")
        self.rtspEdit.setMinimumSize(QSize(0, 31))
        self.rtspEdit.setStyleSheet(u"background-color: rgb(207, 207, 207);")

        self.horizontalLayout.addWidget(self.rtspEdit)

        self.rtspButton = QPushButton(Form)
        self.rtspButton.setObjectName(u"rtspButton")
        self.rtspButton.setStyleSheet(
            u'QPushButton{font-family: "Microsoft YaHei";\n'
            "font-size: 18px;\n"
            "font-weight: bold;\n"
            "color:white;\n"
            "text-align: center center;\n"
            "padding-left: 5px;\n"
            "padding-right: 5px;\n"
            "padding-top: 4px;\n"
            "padding-bottom: 4px;\n"
            "border-style: solid;\n"
            "border-width: 0px;\n"
            "border-color: rgba(255, 255, 255, 255);\n"
            "border-radius: 3px;\n"
            "background-color: rgba(255,255,255,30);}\n"
            "\n"
            "QPushButton:focus{outline: none;}\n"
            "\n"
            'QPushButton::pressed{font-family: "Microsoft YaHei";\n'
            "                     font-size: 16px;\n"
            "                     font-weight: bold;\n"
            "                     color:rgb(200,200,200);\n"
            "                     text-align: center center;\n"
            "                     padding-left: 5px;\n"
            "                     padding-right: 5px;\n"
            "                     padding-top: 4px;\n"
            "                     padding-bottom: 4px;\n"
            "                     border-style: solid;\n"
            "                     border-width: 0px;\n"
            "                     border-color: rgba(255, 255, 255, 255);\n"
            " "
            "                    border-radius: 3px;\n"
            "                     background-color:  rgba(255,255,255,150);}\n"
            "\n"
            "QPushButton::hover {\n"
            "border-style: solid;\n"
            "border-width: 0px;\n"
            "border-radius: 0px;\n"
            "background-color: rgba(255,255,255,50);}"
        )

        self.horizontalLayout.addWidget(self.rtspButton)

        self.retranslateUi(Form)

        QMetaObject.connectSlotsByName(Form)

    # setupUi

    def retranslateUi(self, Form):
        Form.setWindowTitle(QCoreApplication.translate("Form", u"Form", None))
        self.label.setText(QCoreApplication.translate("Form", u"rtsp address:", None))
        self.rtspButton.setText(QCoreApplication.translate("Form", u"confirm", None))

    # retranslateUi
