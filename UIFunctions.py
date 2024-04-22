from main import *
from custom_grips import CustomGrip
from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QEvent, QTimer
from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtWidgets import *
import time

GLOBAL_STATE = False  # max min flag
GLOBAL_TITLE_BAR = True


class UIFuncitons(MainWindow):
    # 展开左侧菜单
    def toggleMenu(self, enable):
        if enable:
            standard = 68  # 左侧菜单的标准宽度
            maxExtend = 180  # 左侧菜单展开时的最大宽度
            width = self.LeftMenuBg.width()  # 现在的菜单宽度

            if width == 68:  # 如果菜单目前是缩起来的
                widthExtended = maxExtend  # 展开后的宽度
            else:
                widthExtended = standard  # 收缩后的宽度

            # 动画效果
            self.animation = QPropertyAnimation(self.LeftMenuBg, b"minimumWidth")
            self.animation.setDuration(500)  # 动画时间（毫秒）
            self.animation.setStartValue(width)  # 动画的起始宽度
            self.animation.setEndValue(widthExtended)  # 动画的结束宽度
            self.animation.setEasingCurve(QEasingCurve.InOutQuint)  # 动画的缓动曲线
            self.animation.start()  # 开始执行动画

    # 展开右侧的设定选单
    def settingBox(self, enable):
        if enable:
            # 获取宽度
            widthRightBox = self.prm_page.width()  # 右侧设定选单的宽度
            widthLeftBox = self.LeftMenuBg.width()  # 左侧菜单的宽度
            maxExtend = 220  # 设定选单展开时的最大宽度
            standard = 0

            # 设定最大宽度
            if widthRightBox == 0:  # 如果右侧设定选单目前是收缩的
                widthExtended = maxExtend  # 展开后的宽度
            else:
                widthExtended = standard  # 收缩后的宽度

            # 设定左侧菜单的动画
            self.left_box = QPropertyAnimation(self.LeftMenuBg, b"minimumWidth")
            self.left_box.setDuration(500)  # 动画时间（毫秒）
            self.left_box.setStartValue(widthLeftBox)  # 动画的起始宽度
            self.left_box.setEndValue(68)  # 动画的结束宽度（收缩的宽度）
            self.left_box.setEasingCurve(QEasingCurve.InOutQuart)  # 动画的缓动曲线

            # 设定右侧设定选单的动画
            self.right_box = QPropertyAnimation(self.prm_page, b"minimumWidth")
            self.right_box.setDuration(500)  # 动画时间（毫秒）
            self.right_box.setStartValue(widthRightBox)  # 动画的起始宽度
            self.right_box.setEndValue(widthExtended)  # 动画的结束宽度
            self.right_box.setEasingCurve(QEasingCurve.InOutQuart)  # 动画的缓动曲线

            # 创建一个平行动画组
            self.group = QParallelAnimationGroup()
            self.group.addAnimation(self.left_box)
            self.group.addAnimation(self.right_box)
            self.group.start()  # 开始执行动画

    # 展开右侧的设定选单
    def cam_settingBox(self, enable):
        if enable:
            # 获取宽度
            widthRightBox = self.prm_page_cam.width()  # 右侧设定选单的宽度
            widthLeftBox = self.LeftMenuBg.width()  # 左侧菜单的宽度
            maxExtend = 220  # 设定选单展开时的最大宽度
            standard = 0

            # 设定最大宽度
            if widthRightBox == 0:  # 如果右侧设定选单目前是收缩的
                widthExtended = maxExtend  # 展开后的宽度
            else:
                widthExtended = standard  # 收缩后的宽度

            # 设定左侧菜单的动画
            self.left_box = QPropertyAnimation(self.LeftMenuBg, b"minimumWidth")
            self.left_box.setDuration(500)  # 动画时间（毫秒）
            self.left_box.setStartValue(widthLeftBox)  # 动画的起始宽度
            self.left_box.setEndValue(68)  # 动画的结束宽度（收缩的宽度）
            self.left_box.setEasingCurve(QEasingCurve.InOutQuart)  # 动画的缓动曲线

            # 设定右侧设定选单的动画
            self.right_box = QPropertyAnimation(self.prm_page_cam, b"minimumWidth")
            self.right_box.setDuration(500)  # 动画时间（毫秒）
            self.right_box.setStartValue(widthRightBox)  # 动画的起始宽度
            self.right_box.setEndValue(widthExtended)  # 动画的结束宽度
            self.right_box.setEasingCurve(QEasingCurve.InOutQuart)  # 动画的缓动曲线

            # 创建一个平行动画组
            self.group = QParallelAnimationGroup()
            self.group.addAnimation(self.left_box)
            self.group.addAnimation(self.right_box)
            self.group.start()  # 开始执行动画

    # 最大化/还原视窗
    def maximize_restore(self):
        global GLOBAL_STATE  # 使用全局变数
        status = GLOBAL_STATE  # 取得全局变数的值
        if status == False:  # 如果视窗不是最大化状态
            GLOBAL_STATE = True  # 设置全局变数为 True（最大化状态）
            self.showMaximized()  # 最大化视窗
            self.max_sf.setToolTip("Restore")  # 更改最大化按钮的提示文本
            self.frame_size_grip.hide()  # 隐藏视窗大小调整按钮
            self.left_grip.hide()  # 隐藏四边调整的按钮
            self.right_grip.hide()
            self.top_grip.hide()
            self.bottom_grip.hide()
        else:
            GLOBAL_STATE = False  # 设置全局变数为 False（非最大化状态）
            self.showNormal()  # 还原视窗（最小化）
            self.resize(self.width() + 1, self.height() + 1)  # 修复最小化后的视窗大小
            self.max_sf.setToolTip("Maximize")  # 更改最大化按钮的提示文本
            self.frame_size_grip.show()  # 显示视窗大小调整按钮
            self.left_grip.show()  # 显示四边调整的按钮
            self.right_grip.show()  # 显示四边调整的按钮
            self.top_grip.show()  # 显示四边调整的按钮
            self.bottom_grip.show()  # 显示四边调整的按钮

    # 视窗控制的定义
    def uiDefinitions(self):
        # 双击标题栏最大化/还原
        def dobleClickMaximizeRestore(event):
            if event.type() == QEvent.MouseButtonDblClick:
                QTimer.singleShot(250, lambda: UIFuncitons.maximize_restore(self))

        self.top.mouseDoubleClickEvent = dobleClickMaximizeRestore

        # 移动视窗 / 最大化 / 还原
        def moveWindow(event):
            if GLOBAL_STATE:  # 如果视窗已最大化，则切换到还原状态
                UIFuncitons.maximize_restore(self)
            if event.buttons() == Qt.LeftButton:  # 移动视窗
                self.move(self.pos() + event.globalPos() - self.dragPos)
                self.dragPos = event.globalPos()

        self.top.mouseMoveEvent = moveWindow

        # 自定义拉伸按钮
        self.left_grip = CustomGrip(self, Qt.LeftEdge, True)
        self.right_grip = CustomGrip(self, Qt.RightEdge, True)
        self.top_grip = CustomGrip(self, Qt.TopEdge, True)
        self.bottom_grip = CustomGrip(self, Qt.BottomEdge, True)

        # 最小化视窗
        self.min_sf.clicked.connect(lambda: self.showMinimized())
        # 最大化/还原视窗
        self.max_sf.clicked.connect(lambda: UIFuncitons.maximize_restore(self))
        # 关闭应用程式
        self.close_button.clicked.connect(self.close)

    # 控制视窗四边的拉伸
    def resize_grips(self):
        # 设置左侧拉伸按钮的位置和大小
        self.left_grip.setGeometry(0, 10, 10, self.height())
        # 设置右侧拉伸按钮的位置和大小
        self.right_grip.setGeometry(self.width() - 10, 10, 10, self.height())
        # 设置上侧拉伸按钮的位置和大小
        self.top_grip.setGeometry(0, 0, self.width(), 10)
        # 设置下侧拉伸按钮的位置和大小
        self.bottom_grip.setGeometry(0, self.height() - 10, self.width(), 10)

    # 显示模组以添加阴影效果
    def shadow_style(self, widget, Color):
        shadow = QGraphicsDropShadowEffect(self)  # 创建阴影效果对象
        shadow.setOffset(8, 8)  # 设定阴影的偏移量
        shadow.setBlurRadius(38)  # 设定阴影的模糊半径
        shadow.setColor(Color)  # 设定阴影的颜色
        widget.setGraphicsEffect(shadow)  # 将阴影效果应用到指定的小部件
