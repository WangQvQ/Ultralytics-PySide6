from ultralytics.engine.predictor import BasePredictor
from ultralytics.models.yolo.detect.predict import DetectionPredictor
from ultralytics.engine.results import Results
from ultralytics.utils import DEFAULT_CFG, LOGGER, SETTINGS, callbacks, ops
from ultralytics.utils.plotting import Annotator, colors, save_one_box
from ultralytics.utils.torch_utils import smart_inference_mode
from ultralytics.utils.files import increment_path
from ultralytics.utils.checks import check_imgsz, check_imshow, check_yaml
from ultralytics.data import load_inference_source
from ultralytics.data.augment import LetterBox, classify_transforms
from ultralytics.cfg import get_cfg, get_save_dir
from ultralytics.trackers import track
from ultralytics import YOLO

from PySide6.QtWidgets import QApplication, QMainWindow, QFileDialog, QMenu
from PySide6.QtGui import QImage, QPixmap, QColor
from PySide6.QtCore import QTimer, QThread, Signal, QObject, QPoint, Qt
from ui.CustomMessageBox import MessageBox
from ui.home import Ui_MainWindow
from UIFunctions import *

from collections import defaultdict
from pathlib import Path
from utils.capnums import Camera
from utils.rtsp_win import Window

import numpy as np
import threading
import traceback
import time
import json
import torch
import sys
import cv2
import os


class YoloPredictor(BasePredictor, QObject):
    # 信号定义，用于与其他部分进行通信
    yolo2main_pre_img = Signal(np.ndarray)  # 原始图像信号
    yolo2main_res_img = Signal(np.ndarray)  # 测试结果信号
    yolo2main_status_msg = Signal(str)  # 检测/暂停/停止/测试完成/错误报告信号
    yolo2main_fps = Signal(str)  # 帧率信号
    yolo2main_labels = Signal(dict)  # 检测目标结果（每个类别的数量）
    yolo2main_progress = Signal(int)  # 完整度信号
    yolo2main_class_num = Signal(int)  # 检测到的类别数量
    yolo2main_target_num = Signal(int)  # 检测到的目标数量

    def __init__(self, cfg=DEFAULT_CFG, overrides=None, _callbacks=None):
        # 调用父类的初始化方法
        super(YoloPredictor, self).__init__()
        # 初始化 PyQt 的 QObject
        QObject.__init__(self)

        # 解析配置文件
        self.args = get_cfg(cfg, overrides)
        # 设置模型保存目录
        self.save_dir = get_save_dir(self.args)
        # 初始化一个标志，标记模型是否已经完成预热（warmup）
        self.done_warmup = False
        # 检查是否要显示图像
        if self.args.show:
            self.args.show = check_imshow(warn=True)

        # GUI 相关的属性
        self.used_model_name = None  # 要使用的检测模型的名称
        self.new_model_name = None  # 实时更改的模型名称
        self.source = ""  # 输入源
        self.stop_dtc = False  # 终止检测的标志
        self.continue_dtc = True  # 暂停检测的标志
        self.save_res = False  # 保存测试结果的标志
        self.save_txt = False  # 保存标签（txt）文件的标志
        self.save_res_cam = False  # 保存webcam测试结果的标志
        self.save_txt_cam = False  # 保存webcam标签（txt）文件的标志
        self.iou_thres = 0.45  # IoU 阈值
        self.conf_thres = 0.25  # 置信度阈值
        self.speed_thres = 0  # 延迟，毫秒
        self.labels_dict = {}  # 返回检测结果的字典
        self.progress_value = 0  # 进度条的值
        self.task = ""

        # 如果设置已完成，可以使用以下属性
        self.model = None
        self.data = self.args.data  # data_dict
        self.imgsz = None
        self.device = None
        self.dataset = None
        self.vid_path, self.vid_writer, self.vid_frame = None, None, None
        self.plotted_img = None
        self.data_path = None
        self.source_type = None
        self.batch = None
        self.results = None
        self.transforms = None
        self.callbacks = _callbacks or callbacks.get_default_callbacks()
        self.txt_path = None
        self._lock = threading.Lock()  # for automatic thread-safe inference
        callbacks.add_integration_callbacks(self)

    # main for detect
    @smart_inference_mode()
    def run(self, *args, **kwargs):
        print(str(self.save_txt) + "sssssssssss")
        print(str(self.save_txt_cam) + "sssssssssss")
        try:
            if self.args.verbose:
                LOGGER.info("")
            # Setup model
            self.yolo2main_status_msg.emit("模型载入中...")
            if not self.model:
                self.setup_model(self.new_model_name)
                self.used_model_name = self.new_model_name

            with self._lock:  # for thread-safe inference
                # Setup source every time predict is called
                self.setup_source(
                    self.source if self.source is not None else self.args.source
                )

                # 检查保存路径/标签
                if (
                    self.save_res
                    or self.save_txt
                    or self.save_res_cam
                    or self.save_txt_cam
                ):
                    (
                        self.save_dir / "labels"
                        if (self.save_txt or self.save_txt_cam)
                        else self.save_dir
                    ).mkdir(parents=True, exist_ok=True)

                # 模型预热
                if not self.done_warmup:
                    self.model.warmup(
                        imgsz=(
                            (
                                1
                                if self.model.pt or self.model.triton
                                else self.dataset.bs
                            ),
                            3,
                            *self.imgsz,
                        )
                    )
                    self.done_warmup = True

                self.seen, self.windows, self.batch, profilers = (
                    0,
                    [],
                    None,
                    (ops.Profile(), ops.Profile(), ops.Profile()),
                )
                # 开始检测
                count = 0  # frame count
                start_time = time.time()  # 用于计算帧率
                # batch = iter(self.dataset)
                for batch in self.dataset:
                    # while True:
                    # 终止检测标志检测
                    if self.stop_dtc:
                        if isinstance(self.vid_writer[-1], cv2.VideoWriter):
                            self.vid_writer[-1].release()  # 释放最后的视讯写入器
                        self.yolo2main_status_msg.emit("检测终止")
                        break

                    # 在中途更改模型
                    if self.used_model_name != self.new_model_name:
                        # self.yolo2main_status_msg.emit('Change Model...')
                        self.setup_model(self.new_model_name)
                        self.used_model_name = self.new_model_name

                    # 暂停开关
                    if self.continue_dtc:
                        # time.sleep(0.001)
                        self.yolo2main_status_msg.emit("检测中...")
                        # batch = next(self.dataset)  # 获取下一个数据

                        self.batch = batch
                        path, im0s, vid_cap, s = batch
                        visualize = (
                            increment_path(self.save_dir / Path(path).stem, mkdir=True)
                            if self.args.visualize
                            else False
                        )

                        # 计算完成度和帧率（待优化）
                        count += 1  # 帧计数 +1
                        if vid_cap:
                            all_count = vid_cap.get(cv2.CAP_PROP_FRAME_COUNT)  # 总帧数
                        else:
                            all_count = 1
                        self.progress_value = int(
                            count / all_count * 1000
                        )  # 进度条（0~1000）
                        if count % 5 == 0 and count >= 5:  # 每5帧计算一次帧率
                            self.yolo2main_fps.emit(
                                str(int(5 / (time.time() - start_time)))
                            )
                            start_time = time.time()
                        # Preprocess
                        with profilers[0]:
                            if self.task == "Classify":
                                im = self.classify_preprocess(im0s)
                            else:
                                im = self.preprocess(im0s)
                            # elif self.task == 'Detect' or self.task == 'Pose' or self.task == 'Segment':
                            #     im = self.preprocess(im0s)

                        # Inference
                        with profilers[1]:
                            preds = self.inference(im, *args, **kwargs)
                            # if self.args.embed:
                            # yield from [preds] if isinstance(preds, torch.Tensor) else preds  # yield embedding tensors
                            # continue

                        # Postprocess
                        with profilers[2]:
                            if self.task == "Classify":
                                self.results = self.classify_postprocess(
                                    preds, im, im0s
                                )
                            elif self.task == "Detect":
                                self.results = self.postprocess(preds, im, im0s)
                            elif self.task == "Pose":
                                self.results = self.pose_postprocess(preds, im, im0s)
                            elif self.task == "Segment":
                                self.results = self.segment_postprocess(preds, im, im0s)

                            elif self.task == "Track":
                                model = YOLO(self.used_model_name)
                                self.results = model.track(
                                    source=self.source, tracker="bytetrack.yaml"
                                )
                                print(self.results)
                                # pass
                        self.run_callbacks("on_predict_postprocess_end")
                        # Visualize, save, write results
                        n = len(im0s)
                        for i in range(n):
                            self.seen += 1
                            self.results[i].speed = {
                                "preprocess": profilers[0].dt * 1e3 / n,
                                "inference": profilers[1].dt * 1e3 / n,
                                "postprocess": profilers[2].dt * 1e3 / n,
                            }
                            p, im0 = (
                                path[i],
                                (None if self.source_type.tensor else im0s[i].copy()),
                            )
                            p = Path(p)
                            label_str = self.write_results(
                                i, self.results, (p, im, im0)
                            )

                            # 标签和数字字典
                            class_nums = 0
                            target_nums = 0
                            self.labels_dict = {}
                            if "no detections" in label_str:
                                im0 = im0
                                pass
                            else:
                                im0 = self.plotted_img
                                for ii in label_str.split(",")[:-1]:
                                    nums, label_name = ii.split("~")
                                    if ":" in nums:
                                        _, nums = nums.split(":")
                                    self.labels_dict[label_name] = int(nums)
                                    target_nums += int(nums)
                                    class_nums += 1
                            if self.save_res:
                                self.save_preds(vid_cap, i, str(self.save_dir / p.name))

                            # 发送测试结果
                            self.yolo2main_res_img.emit(im0)  # 检测后
                            self.yolo2main_pre_img.emit(
                                im0s if isinstance(im0s, np.ndarray) else im0s[0]
                            )  # 检测前
                            # self.yolo2main_labels.emit(self.labels_dict)        # webcam 需要更改 def write_results
                            self.yolo2main_class_num.emit(class_nums)
                            self.yolo2main_target_num.emit(target_nums)

                            if self.speed_thres != 0:
                                time.sleep(self.speed_thres / 1000)  # 延迟，毫秒

                        self.yolo2main_progress.emit(self.progress_value)  # 进度条

                    # 检测完成
                    if not self.source_type.webcam and count + 1 >= all_count:
                        if isinstance(self.vid_writer[-1], cv2.VideoWriter):
                            self.vid_writer[-1].release()  # 释放最后的视频写入器
                        self.yolo2main_status_msg.emit("检测完成")
                        break

        except Exception as e:
            pass
            traceback.print_exc()
            print(f"Error: {e}")
            self.yolo2main_status_msg.emit("%s" % e)

    def inference(self, img, *args, **kwargs):
        """Runs inference on a given image using the specified model and arguments."""
        visualize = (
            increment_path(self.save_dir / Path(self.batch[0][0]).stem, mkdir=True)
            if self.args.visualize and (not self.source_type.tensor)
            else False
        )
        return self.model(
            img,
            augment=self.args.augment,
            visualize=visualize,
            embed=self.args.embed,
            *args,
            **kwargs,
        )

    def get_annotator(self, img):
        return Annotator(
            img, line_width=self.args.line_thickness, example=str(self.model.names)
        )

    def classify_preprocess(self, img):
        """Converts input image to model-compatible data type."""
        if not isinstance(img, torch.Tensor):
            img = torch.stack([self.transforms(im) for im in img], dim=0)
        img = (img if isinstance(img, torch.Tensor) else torch.from_numpy(img)).to(
            self.model.device
        )
        return img.half() if self.model.fp16 else img.float()  # uint8 to fp16/32

    def classify_postprocess(self, preds, img, orig_imgs):
        """Post-processes predictions to return Results objects."""
        if not isinstance(
            orig_imgs, list
        ):  # input images are a torch.Tensor, not a list
            orig_imgs = ops.convert_torch2numpy_batch(orig_imgs)

        results = []
        for i, pred in enumerate(preds):
            orig_img = orig_imgs[i]
            img_path = self.batch[0][i]
            results.append(
                Results(
                    orig_img=orig_img, path=img_path, names=self.model.names, probs=pred
                )
            )
        return results

    def preprocess(self, img):
        not_tensor = not isinstance(img, torch.Tensor)
        if not_tensor:
            img = np.stack(self.pre_transform(img))
            img = img[..., ::-1].transpose(
                (0, 3, 1, 2)
            )  # BGR to RGB, BHWC to BCHW, (n, 3, h, w)
            img = np.ascontiguousarray(img)  # contiguous
            img = torch.from_numpy(img)

        img = img.to(self.device)
        img = img.half() if self.model.fp16 else img.float()  # uint8 to fp16/32
        if not_tensor:
            img /= 255  # 0 - 255 to 0.0 - 1.0
        return img

    def postprocess(self, preds, img, orig_img):
        ### important
        preds = ops.non_max_suppression(
            preds,
            self.conf_thres,
            self.iou_thres,
            agnostic=self.args.agnostic_nms,
            max_det=self.args.max_det,
            classes=self.args.classes,
        )

        results = []
        for i, pred in enumerate(preds):
            orig_img = orig_img[i] if isinstance(orig_img, list) else orig_img
            shape = orig_img.shape
            pred[:, :4] = ops.scale_boxes(img.shape[2:], pred[:, :4], shape).round()
            path, _, _, _ = self.batch
            img_path = path[i] if isinstance(path, list) else path
            results.append(
                Results(
                    orig_img=orig_img, path=img_path, names=self.model.names, boxes=pred
                )
            )
        return results

    def pose_postprocess(self, preds, img, orig_imgs):
        """Return detection results for a given input image or list of images."""
        preds = ops.non_max_suppression(
            preds,
            self.conf_thres,
            self.iou_thres,
            agnostic=self.args.agnostic_nms,
            max_det=self.args.max_det,
            classes=self.args.classes,
            nc=len(self.model.names),
        )

        if not isinstance(
            orig_imgs, list
        ):  # input images are a torch.Tensor, not a list
            orig_imgs = ops.convert_torch2numpy_batch(orig_imgs)

        results = []
        for i, pred in enumerate(preds):
            orig_img = orig_imgs[i]
            pred[:, :4] = ops.scale_boxes(
                img.shape[2:], pred[:, :4], orig_img.shape
            ).round()
            pred_kpts = (
                pred[:, 6:].view(len(pred), *self.model.kpt_shape)
                if len(pred)
                else pred[:, 6:]
            )
            pred_kpts = ops.scale_coords(img.shape[2:], pred_kpts, orig_img.shape)
            img_path = self.batch[0][i]
            results.append(
                Results(
                    orig_img,
                    path=img_path,
                    names=self.model.names,
                    boxes=pred[:, :6],
                    keypoints=pred_kpts,
                )
            )
        return results

    def segment_postprocess(self, preds, img, orig_imgs):
        """Applies non-max suppression and processes detections for each image in an input batch."""
        p = ops.non_max_suppression(
            preds[0],
            self.conf_thres,
            self.iou_thres,
            agnostic=self.args.agnostic_nms,
            max_det=self.args.max_det,
            nc=len(self.model.names),
            classes=self.args.classes,
        )

        if not isinstance(
            orig_imgs, list
        ):  # input images are a torch.Tensor, not a list
            orig_imgs = ops.convert_torch2numpy_batch(orig_imgs)

        results = []
        proto = (
            preds[1][-1] if len(preds[1]) == 3 else preds[1]
        )  # second output is len 3 if pt, but only 1 if exported
        for i, pred in enumerate(p):
            orig_img = orig_imgs[i]
            img_path = self.batch[0][i]
            if not len(pred):  # save empty boxes
                masks = None
            elif self.args.retina_masks:
                pred[:, :4] = ops.scale_boxes(
                    img.shape[2:], pred[:, :4], orig_img.shape
                )
                masks = ops.process_mask_native(
                    proto[i], pred[:, 6:], pred[:, :4], orig_img.shape[:2]
                )  # HWC
            else:
                masks = ops.process_mask(
                    proto[i], pred[:, 6:], pred[:, :4], img.shape[2:], upsample=True
                )  # HWC
                pred[:, :4] = ops.scale_boxes(
                    img.shape[2:], pred[:, :4], orig_img.shape
                )
            results.append(
                Results(
                    orig_img,
                    path=img_path,
                    names=self.model.names,
                    boxes=pred[:, :6],
                    masks=masks,
                )
            )
        return results

    def pre_transform(self, img):
        same_shapes = all(x.shape == img[0].shape for x in img)
        letterbox = LetterBox(
            self.imgsz, auto=same_shapes and self.model.pt, stride=self.model.stride
        )
        return [letterbox(image=x) for x in img]

    def setup_source(self, source):
        self.imgsz = check_imgsz(
            self.args.imgsz, stride=self.model.stride, min_dim=2
        )  # check image size
        self.transforms = (
            getattr(self.model.model, "transforms", classify_transforms(self.imgsz[0]))
            if self.task == "Classify"
            else None
        )
        self.dataset = load_inference_source(
            source=source,
            imgsz=self.imgsz,
            vid_stride=self.args.vid_stride,
            buffer=self.args.stream_buffer,
        )
        self.source_type = self.dataset.source_type
        if not getattr(self, "stream", True) and (
            self.dataset.mode == "stream"  # streams
            or len(self.dataset) > 1000  # images
            or any(getattr(self.dataset, "video_flag", [False]))
        ):  # videos
            LOGGER.warning(STREAM_WARNING)
        self.vid_path = [None] * self.dataset.bs
        self.vid_writer = [None] * self.dataset.bs
        self.vid_frame = [None] * self.dataset.bs

    def write_results(self, idx, results, batch):
        """Write inference results to a file or directory."""
        p, im, _ = batch
        log_string = ""
        if len(im.shape) == 3:
            im = im[None]  # expand for batch dim

        if (
            self.source_type.webcam
            or self.source_type.from_img
            or self.source_type.tensor
        ):  # batch_size >= 1
            log_string += f"{idx}: "
            frame = self.dataset.count
        else:
            frame = getattr(self.dataset, "frame", 0)
        self.data_path = p
        self.txt_path = str(self.save_dir / "labels" / p.stem) + (
            "" if self.dataset.mode == "image" else f"_{frame}"
        )
        # log_string += '%gx%g ' % im.shape[2:]  # print string

        result = results[idx]

        if self.task == "Classify":
            prob = results[idx].probs
            # for c in prob.top5:
            #     print(c)
        else:
            det = results[idx].boxes
            if len(det) == 0:
                return f"{log_string}(no detections), "  # if no, send this~~

            for c in det.cls.unique():
                n = (det.cls == c).sum()  # detections per class
                log_string += f"{n}~{self.model.names[int(c)]},"

        if (
            self.save_res or self.save_res_cam or self.args.save or self.args.show
        ):  # Add bbox to image
            plot_args = {
                "line_width": self.args.line_width,
                "boxes": self.args.show_boxes,
                "conf": self.args.show_conf,
                "labels": self.args.show_labels,
            }
            if not self.args.retina_masks:
                plot_args["im_gpu"] = im[idx]
            self.plotted_img = result.plot(**plot_args)
        # Write
        # if self.save_res_cam:
        #     result.save(str(self.save_dir / p.name))
        if self.save_txt or self.save_txt_cam:
            result.save_txt(f"{self.txt_path}.txt", save_conf=self.args.save_conf)
        if self.args.save_crop:
            result.save_crop(
                save_dir=self.save_dir / "crops",
                file_name=self.data_path.stem
                + ("" if self.dataset.mode == "image" else f"_{frame}"),
            )

        return log_string


class MainWindow(QMainWindow, Ui_MainWindow):
    main2yolo_begin_sgl = Signal()  # 主视窗向 YOLO 实例发送执行信号

    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)

        # 基本介面设置
        self.setupUi(self)
        self.setAttribute(Qt.WA_TranslucentBackground)  # 圆角透明
        self.setWindowFlags(Qt.FramelessWindowHint)  # 设置窗口标志: 隐藏窗口边框
        UIFuncitons.uiDefinitions(self)  # 自定义介面定义

        # 初始页面
        self.task = ""
        self.PageIndex = 1
        self.content.setCurrentIndex(self.PageIndex)
        self.pushButton_detect.clicked.connect(self.button_detect)
        self.pushButton_pose.clicked.connect(self.button_pose)
        self.pushButton_classify.clicked.connect(self.button_classify)
        self.pushButton_segment.clicked.connect(self.button_segment)
        # self.pushButton_track.setEnabled(False)

        self.src_file_button.setEnabled(False)
        self.src_cam_button.setEnabled(False)
        self.src_rtsp_button.setEnabled(False)
        ####################################image or video####################################
        # 显示模块阴影
        UIFuncitons.shadow_style(self, self.Class_QF, QColor(162, 129, 247))
        UIFuncitons.shadow_style(self, self.Target_QF, QColor(251, 157, 139))
        UIFuncitons.shadow_style(self, self.Fps_QF, QColor(170, 128, 213))
        UIFuncitons.shadow_style(self, self.Model_QF, QColor(64, 186, 193))

        # YOLO-v8 线程
        self.yolo_predict = YoloPredictor()  # 创建 YOLO 实例
        self.select_model = self.model_box.currentText()  # 默认模型

        self.yolo_thread = QThread()  # 创建 YOLO 线程
        self.yolo_predict.yolo2main_pre_img.connect(
            lambda x: self.show_image(x, self.pre_video)
        )
        self.yolo_predict.yolo2main_res_img.connect(
            lambda x: self.show_image(x, self.res_video)
        )
        self.yolo_predict.yolo2main_status_msg.connect(lambda x: self.show_status(x))
        self.yolo_predict.yolo2main_fps.connect(lambda x: self.fps_label.setText(x))
        self.yolo_predict.yolo2main_class_num.connect(
            lambda x: self.Class_num.setText(str(x))
        )
        self.yolo_predict.yolo2main_target_num.connect(
            lambda x: self.Target_num.setText(str(x))
        )
        self.yolo_predict.yolo2main_progress.connect(
            lambda x: self.progress_bar.setValue(x)
        )
        self.main2yolo_begin_sgl.connect(self.yolo_predict.run)
        self.yolo_predict.moveToThread(self.yolo_thread)

        self.Qtimer_ModelBox = QTimer(self)  # 定时器: 每 2 秒监控模型文件的变化
        self.Qtimer_ModelBox.timeout.connect(self.ModelBoxRefre)
        self.Qtimer_ModelBox.start(2000)

        # 模型参数
        self.model_box.currentTextChanged.connect(self.change_model)
        self.iou_spinbox.valueChanged.connect(
            lambda x: self.change_val(x, "iou_spinbox")
        )  # iou 文本框
        self.iou_slider.valueChanged.connect(
            lambda x: self.change_val(x, "iou_slider")
        )  # iou 滚动条
        self.conf_spinbox.valueChanged.connect(
            lambda x: self.change_val(x, "conf_spinbox")
        )  # conf 文本框
        self.conf_slider.valueChanged.connect(
            lambda x: self.change_val(x, "conf_slider")
        )  # conf 滚动条
        self.speed_spinbox.valueChanged.connect(
            lambda x: self.change_val(x, "speed_spinbox")
        )  # speed 文本框
        self.speed_slider.valueChanged.connect(
            lambda x: self.change_val(x, "speed_slider")
        )  # speed 滚动条

        # 提示窗口初始化
        self.Class_num.setText("--")
        self.Target_num.setText("--")
        self.fps_label.setText("--")
        self.Model_name.setText(self.select_model)

        # 选择检测来源
        self.src_file_button.clicked.connect(self.open_src_file)  # 选择本地文件
        self.src_rtsp_button.clicked.connect(
            self.show_status("The function has not yet been implemented.")
        )  # 选择 RTSP

        # 开始测试按钮
        self.run_button.clicked.connect(self.run_or_continue)  # 暂停/开始
        self.stop_button.clicked.connect(self.stop)  # 终止

        # 其他功能按钮
        self.save_res_button.toggled.connect(self.is_save_res)  # 保存图片选项
        self.save_txt_button.toggled.connect(self.is_save_txt)  # 保存标签选项
        ####################################image or video####################################

        ####################################camera####################################
        self.cam_data = np.array([])
        # 显示cam模块阴影
        UIFuncitons.shadow_style(self, self.Class_QF_cam, QColor(162, 129, 247))
        UIFuncitons.shadow_style(self, self.Target_QF_cam, QColor(251, 157, 139))
        UIFuncitons.shadow_style(self, self.Fps_QF_cam, QColor(170, 128, 213))
        UIFuncitons.shadow_style(self, self.Model_QF_cam, QColor(64, 186, 193))

        # YOLO-v8-cam线程
        self.yolo_predict_cam = YoloPredictor()  # 创建 YOLO 实例
        self.select_model_cam = self.model_box_cam.currentText()  # 默认模型

        self.yolo_thread_cam = QThread()  # 创建 YOLO 线程
        self.yolo_predict_cam.yolo2main_pre_img.connect(
            lambda c: self.cam_show_image(c, self.pre_cam)
        )
        self.yolo_predict_cam.yolo2main_res_img.connect(
            lambda c: self.cam_show_image(c, self.res_cam)
        )
        self.yolo_predict_cam.yolo2main_status_msg.connect(
            lambda c: self.cam_show_status(c)
        )
        self.yolo_predict_cam.yolo2main_fps.connect(
            lambda c: self.fps_label_cam.setText(c)
        )
        self.yolo_predict_cam.yolo2main_class_num.connect(
            lambda c: self.Class_num_cam.setText(str(c))
        )
        self.yolo_predict_cam.yolo2main_target_num.connect(
            lambda c: self.Target_num_cam.setText(str(c))
        )
        # self.yolo_predict_cam.yolo2main_progress.connect(lambda c: self.progress_bar_cam.setValue(c))
        self.yolo_predict_cam.yolo2main_progress.connect(
            self.progress_bar_cam.setValue(0)
        )
        self.main2yolo_begin_sgl.connect(self.yolo_predict_cam.run)
        self.yolo_predict_cam.moveToThread(self.yolo_thread_cam)

        self.Qtimer_ModelBox_cam = QTimer(self)  # 定时器: 每 2 秒监控模型文件的变化
        self.Qtimer_ModelBox_cam.timeout.connect(self.ModelBoxRefre)
        self.Qtimer_ModelBox_cam.start(2000)

        # cam模型参数
        self.model_box_cam.currentTextChanged.connect(self.cam_change_model)
        self.iou_spinbox_cam.valueChanged.connect(
            lambda c: self.cam_change_val(c, "iou_spinbox_cam")
        )  # iou 文本框
        self.iou_slider_cam.valueChanged.connect(
            lambda c: self.cam_change_val(c, "iou_slider_cam")
        )  # iou 滚动条
        self.conf_spinbox_cam.valueChanged.connect(
            lambda c: self.cam_change_val(c, "conf_spinbox_cam")
        )  # conf 文本框
        self.conf_slider_cam.valueChanged.connect(
            lambda c: self.cam_change_val(c, "conf_slider_cam")
        )  # conf 滚动条
        self.speed_spinbox_cam.valueChanged.connect(
            lambda c: self.cam_change_val(c, "speed_spinbox_cam")
        )  # speed 文本框
        self.speed_slider_cam.valueChanged.connect(
            lambda c: self.cam_change_val(c, "speed_slider_cam")
        )  # speed 滚动条

        # 提示窗口初始化
        self.Class_num_cam.setText("--")
        self.Target_num_cam.setText("--")
        self.fps_label_cam.setText("--")
        self.Model_name_cam.setText(self.select_model_cam)

        # 选择检测来源
        self.src_cam_button.clicked.connect(self.cam_button)  # 选择摄像机

        # 开始测试按钮
        self.run_button_cam.clicked.connect(self.cam_run_or_continue)  # 暂停/开始
        self.stop_button_cam.clicked.connect(self.cam_stop)  # 终止

        # 其他功能按钮
        self.save_res_button_cam.toggled.connect(self.cam_is_save_res)  # 保存图片选项
        self.save_txt_button_cam.toggled.connect(self.cam_is_save_txt)  # 保存标签选项
        ####################################camera####################################

        self.ToggleBotton.clicked.connect(
            lambda: UIFuncitons.toggleMenu(self, True)
        )  # 左侧导航按钮

        # 初始化
        self.load_config()

    def button_classify(self):  # 触发button_detect后的事件
        self.task = "Classify"
        self.yolo_predict.task = self.task
        self.yolo_predict_cam.task = self.task

        self.content.setCurrentIndex(0)
        self.src_file_button.setEnabled(True)
        self.src_cam_button.setEnabled(True)
        self.src_rtsp_button.setEnabled(True)
        self.settings_button.clicked.connect(
            lambda: UIFuncitons.settingBox(self, True)
        )  # 右上方设置按钮

        # 读取模型文件夹
        self.pt_list = os.listdir("./models/classify/")
        self.pt_list = [
            file for file in self.pt_list if file.endswith((".pt", "onnx", "engine"))
        ]
        self.pt_list.sort(
            key=lambda x: os.path.getsize("./models/classify/" + x)
        )  # 按文件大小排序
        self.model_box.clear()
        self.model_box.addItems(self.pt_list)
        self.yolo_predict.new_model_name = "./models/classify/%s" % self.select_model
        self.yolo_predict_cam.new_model_name = (
            "./models/classify/%s" % self.select_model_cam
        )

        # 读取cam模型文件夹
        self.pt_list_cam = os.listdir("./models/classify/")
        self.pt_list_cam = [
            file
            for file in self.pt_list_cam
            if file.endswith((".pt", "onnx", "engine"))
        ]
        self.pt_list_cam.sort(
            key=lambda x: os.path.getsize("./models/classify/" + x)
        )  # 按文件大小排序
        self.model_box_cam.clear()
        self.model_box_cam.addItems(self.pt_list_cam)
        self.show_status("目前页面：image or video检测页面，Mode：Classify")

    def button_detect(self):  # 触发button_detect后的事件
        self.task = "Detect"
        self.yolo_predict.task = self.task
        self.yolo_predict_cam.task = self.task
        self.yolo_predict.new_model_name = "./models/detect/%s" % self.select_model
        self.yolo_predict_cam.new_model_name = (
            "./models/detect/%s" % self.select_model_cam
        )
        self.content.setCurrentIndex(0)
        self.src_file_button.setEnabled(True)
        self.src_cam_button.setEnabled(True)
        self.src_rtsp_button.setEnabled(True)
        self.settings_button.clicked.connect(
            lambda: UIFuncitons.settingBox(self, True)
        )  # 右上方设置按钮

        # 读取模型文件夹
        self.pt_list = os.listdir("./models/detect/")
        self.pt_list = [
            file for file in self.pt_list if file.endswith((".pt", "onnx", "engine"))
        ]
        self.pt_list.sort(
            key=lambda x: os.path.getsize("./models/detect/" + x)
        )  # 按文件大小排序
        self.model_box.clear()
        self.model_box.addItems(self.pt_list)
        self.yolo_predict.new_model_name = "./models/detect/%s" % self.select_model
        self.yolo_predict_cam.new_model_name = (
            "./models/detect/%s" % self.select_model_cam
        )

        # 读取cam模型文件夹
        self.pt_list_cam = os.listdir("./models/detect/")
        self.pt_list_cam = [
            file
            for file in self.pt_list_cam
            if file.endswith((".pt", "onnx", "engine"))
        ]
        self.pt_list_cam.sort(
            key=lambda x: os.path.getsize("./models/detect/" + x)
        )  # 按文件大小排序
        self.model_box_cam.clear()
        self.model_box_cam.addItems(self.pt_list_cam)
        self.show_status("目前页面：image or video检测页面，Mode：Detect")

    def button_pose(self):  # 触发button_detect后的事件
        self.task = "Pose"
        self.yolo_predict.task = self.task
        self.yolo_predict_cam.task = self.task
        self.yolo_predict.new_model_name = "./models/pose/%s" % self.select_model
        self.yolo_predict_cam.new_model_name = (
            "./models/pose/%s" % self.select_model_cam
        )
        self.content.setCurrentIndex(0)
        self.src_file_button.setEnabled(True)
        self.src_cam_button.setEnabled(True)
        self.src_rtsp_button.setEnabled(True)
        self.settings_button.clicked.connect(
            lambda: UIFuncitons.settingBox(self, True)
        )  # 右上方设置按钮

        # 读取模型文件夹
        self.pt_list = os.listdir("./models/pose/")
        self.pt_list = [
            file for file in self.pt_list if file.endswith((".pt", "onnx", "engine"))
        ]
        self.pt_list.sort(
            key=lambda x: os.path.getsize("./models/pose/" + x)
        )  # 按文件大小排序
        self.model_box.clear()
        self.model_box.addItems(self.pt_list)
        self.yolo_predict.new_model_name = "./models/pose/%s" % self.select_model
        self.yolo_predict_cam.new_model_name = (
            "./models/pose/%s" % self.select_model_cam
        )

        # 读取cam模型文件夹
        self.pt_list_cam = os.listdir("./models/pose/")
        self.pt_list_cam = [
            file
            for file in self.pt_list_cam
            if file.endswith((".pt", "onnx", "engine"))
        ]
        self.pt_list_cam.sort(
            key=lambda x: os.path.getsize("./models/pose/" + x)
        )  # 按文件大小排序
        self.model_box_cam.clear()
        self.model_box_cam.addItems(self.pt_list_cam)
        self.show_status("目前页面：image or video检测页面，Mode：Pose")

    def button_segment(self):  # 触发button_detect后的事件
        self.task = "Segment"
        self.yolo_predict.task = self.task
        self.yolo_predict_cam.task = self.task
        self.yolo_predict.new_model_name = "./models/segment/%s" % self.select_model
        self.yolo_predict_cam.new_model_name = (
            "./models/segment/%s" % self.select_model_cam
        )
        self.content.setCurrentIndex(0)
        self.src_file_button.setEnabled(True)
        self.src_cam_button.setEnabled(False)
        self.src_rtsp_button.setEnabled(True)
        self.settings_button.clicked.connect(
            lambda: UIFuncitons.settingBox(self, True)
        )  # 右上方设置按钮

        # 读取模型文件夹
        self.pt_list = os.listdir("./models/segment/")
        self.pt_list = [
            file for file in self.pt_list if file.endswith((".pt", "onnx", "engine"))
        ]
        self.pt_list.sort(
            key=lambda x: os.path.getsize("./models/segment/" + x)
        )  # 按文件大小排序
        self.model_box.clear()
        self.model_box.addItems(self.pt_list)
        self.yolo_predict.new_model_name = "./models/segment/%s" % self.select_model
        self.yolo_predict_cam.new_model_name = (
            "./models/segment/%s" % self.select_model_cam
        )

        # 读取cam模型文件夹
        self.pt_list_cam = os.listdir("./models/segment/")
        self.pt_list_cam = [
            file
            for file in self.pt_list_cam
            if file.endswith((".pt", "onnx", "engine"))
        ]
        self.pt_list_cam.sort(
            key=lambda x: os.path.getsize("./models/segment/" + x)
        )  # 按文件大小排序
        self.model_box_cam.clear()
        self.model_box_cam.addItems(self.pt_list_cam)
        self.show_status("目前页面：image or video检测页面，Mode：Segment")

    def button_track(self):  # 触发button_detect后的事件
        self.task = "Track"
        self.yolo_predict.task = self.task
        self.yolo_predict_cam.task = self.task
        self.yolo_predict.new_model_name = "./models/track/%s" % self.select_model
        self.yolo_predict_cam.new_model_name = (
            "./models/track/%s" % self.select_model_cam
        )
        self.content.setCurrentIndex(0)
        self.src_file_button.setEnabled(True)
        self.src_cam_button.setEnabled(True)
        self.src_rtsp_button.setEnabled(True)
        self.settings_button.clicked.connect(
            lambda: UIFuncitons.settingBox(self, True)
        )  # 右上方设置按钮

        # 读取模型文件夹
        self.pt_list = os.listdir("./models/track/")
        self.pt_list = [
            file for file in self.pt_list if file.endswith((".pt", "onnx", "engine"))
        ]
        self.pt_list.sort(
            key=lambda x: os.path.getsize("./models/track/" + x)
        )  # 按文件大小排序
        self.model_box.clear()
        self.model_box.addItems(self.pt_list)
        self.yolo_predict.new_model_name = "./models/track/%s" % self.select_model
        self.yolo_predict_cam.new_model_name = (
            "./models/track/%s" % self.select_model_cam
        )

        # 读取cam模型文件夹
        self.pt_list_cam = os.listdir("./models/track/")
        self.pt_list_cam = [
            file
            for file in self.pt_list_cam
            if file.endswith((".pt", "onnx", "engine"))
        ]
        self.pt_list_cam.sort(
            key=lambda x: os.path.getsize("./models/track/" + x)
        )  # 按文件大小排序
        self.model_box_cam.clear()
        self.model_box_cam.addItems(self.pt_list_cam)
        self.show_status("目前页面：image or video检测页面，Mode：Track")

    ####################################image or video####################################
    # 选择本地档案
    def open_src_file(self):
        if self.task == "Classify":
            self.show_status("目前页面：image or video检测页面，Mode：Classify")
        if self.task == "Detect":
            self.show_status("目前页面：image or video检测页面，Mode：Detect")
        if self.task == "Pose":
            self.show_status("目前页面：image or video检测页面，Mode：Pose")
        if self.task == "Segment":
            self.show_status("目前页面：image or video检测页面，Mode：Segment")
        if self.task == "Track":
            self.show_status("目前页面：image or video检测页面，Mode：Track")

        # 结束cam线程，节省资源
        if self.yolo_thread_cam.isRunning():
            self.yolo_thread_cam.quit()  # 结束线程
            self.cam_stop()
        # 0:image/video page
        # 1:home page
        # 2:camera page
        if self.PageIndex != 0:
            self.PageIndex = 0
            self.content.setCurrentIndex(self.PageIndex)
            self.settings_button.clicked.connect(
                lambda: UIFuncitons.settingBox(self, True)
            )  # 右上方设置按钮

        if self.PageIndex == 0:
            # 设置配置档路径
            config_file = "config/fold.json"

            # 读取配置档内容
            config = json.load(open(config_file, "r", encoding="utf-8"))

            # 获取上次打开的资料夹路径
            open_fold = config["open_fold"]

            # 如果上次打开的资料夹不存在，则使用当前工作目录
            if not os.path.exists(open_fold):
                open_fold = os.getcwd()

            # 通过文件对话框让用户选择图片或影片档案
            if self.task == "Track":
                name, _ = QFileDialog.getOpenFileName(
                    self, "Video", open_fold, "Pic File(*.mp4 *.mkv *.avi *.flv)"
                )
            else:
                name, _ = QFileDialog.getOpenFileName(
                    self,
                    "Video/image",
                    open_fold,
                    "Pic File(*.mp4 *.mkv *.avi *.flv *.jpg *.png)",
                )

            # 如果用户选择了档案
            if name:
                # 将所选档案的路径设置为 yolo_predict 的 source
                self.yolo_predict.source = name

                # 显示档案载入状态
                self.show_status("载入档案：{}".format(os.path.basename(name)))

                # 更新配置档中的上次打开的资料夹路径
                config["open_fold"] = os.path.dirname(name)

                # 将更新后的配置档写回到档案中
                config_json = json.dumps(config, ensure_ascii=False, indent=2)
                with open(config_file, "w", encoding="utf-8") as f:
                    f.write(config_json)

                # 停止检测
                self.stop()

    # 主视窗显示原始图片和检测结果
    @staticmethod
    def show_image(img_src, label):
        try:
            # 获取原始图片的高度、宽度和通道数
            ih, iw, _ = img_src.shape

            # 获取标签(label)的宽度和高度
            w = label.geometry().width()
            h = label.geometry().height()

            # 保持原始数据比例
            if iw / w > ih / h:
                scal = w / iw
                nw = w
                nh = int(scal * ih)
                img_src_ = cv2.resize(img_src, (nw, nh))
            else:
                scal = h / ih
                nw = int(scal * iw)
                nh = h
                img_src_ = cv2.resize(img_src, (nw, nh))

            # 将图片转换为RGB格式
            frame = cv2.cvtColor(img_src_, cv2.COLOR_BGR2RGB)

            # 将图片数据转换为Qt的图片对象
            img = QImage(
                frame.data,
                frame.shape[1],
                frame.shape[0],
                frame.shape[2] * frame.shape[1],
                QImage.Format_RGB888,
            )

            # 将图片显示在标签(label)上
            label.setPixmap(QPixmap.fromImage(img))

        except Exception as e:
            # 处理异常，印出错误信息
            print(repr(e))

    # 控制开始/暂停检测
    def run_or_continue(self):
        # 检查 YOLO 预测的来源是否为空
        if self.yolo_predict.source == "":
            self.show_status("开始侦测前请选择图片或影片来源...")
            self.run_button.setChecked(False)
        else:
            # 设置 YOLO 预测的停止标志为 False
            self.yolo_predict.stop_dtc = False

            # 如果开始按钮被勾选
            if self.run_button.isChecked():
                self.run_button.setChecked(True)  # 启动按钮
                self.save_txt_button.setEnabled(False)  # 启动检测后禁止勾选保存
                self.save_res_button.setEnabled(False)
                self.show_status("检测中...")
                self.yolo_predict.continue_dtc = True  # 控制 YOLO 是否暂停
                if not self.yolo_thread.isRunning():
                    self.yolo_thread.start()
                    self.main2yolo_begin_sgl.emit()

            # 如果开始按钮未被勾选，表示暂停检测
            else:
                self.yolo_predict.continue_dtc = False
                self.show_status("检测暂停...")
                self.run_button.setChecked(False)  # 停止按钮

    # 显示底部状态栏信息
    def show_status(self, msg):
        # 设置状态栏文字
        self.status_bar.setText(msg)

        # 根据不同的状态信息执行相应的操作
        if msg == "Detection completed" or msg == "检测完成":
            # 启用保存结果和保存文本的按钮
            self.save_res_button.setEnabled(True)
            self.save_txt_button.setEnabled(True)

            # 将检测开关按钮设置为未勾选状态
            self.run_button.setChecked(False)

            # 将进度条的值设置为0
            self.progress_bar.setValue(0)

            # 如果 YOLO 线程正在运行，则终止该线程
            if self.yolo_thread.isRunning():
                self.yolo_thread.quit()  # 结束处理

        elif msg == "Detection terminated!" or msg == "检测终止":
            # 启用保存结果和保存文本的按钮
            self.save_res_button.setEnabled(True)
            self.save_txt_button.setEnabled(True)

            # 将检测开关按钮设置为未勾选状态
            self.run_button.setChecked(False)

            # 将进度条的值设置为0
            self.progress_bar.setValue(0)

            # 如果 YOLO 线程正在运行，则终止该线程
            if self.yolo_thread.isRunning():
                self.yolo_thread.quit()  # 结束处理

            # 清空影像显示
            self.pre_video.clear()  # 清除原始图像
            self.res_video.clear()  # 清除检测结果图像
            self.Class_num.setText("--")  # 显示的类别数目
            self.Target_num.setText("--")  # 显示的目标数目
            self.fps_label.setText("--")  # 显示的帧率信息

    # 保存测试结果按钮 -- 图片/视频
    def is_save_res(self):
        if self.save_res_button.checkState() == Qt.CheckState.Unchecked:
            # 显示消息，提示运行图片结果不会保存
            self.show_status("NOTE: Run image results are not saved.")

            # 将 YOLO 实例的保存结果的标志设置为 False
            self.yolo_predict.save_res = False
        elif self.save_res_button.checkState() == Qt.CheckState.Checked:
            # 显示消息，提示运行图片结果将会保存
            self.show_status("NOTE: Run image results will be saved.")

            # 将 YOLO 实例的保存结果的标志设置为 True
            self.yolo_predict.save_res = True

    # 保存测试结果按钮 -- 标签（txt）
    def is_save_txt(self):
        if self.save_txt_button.checkState() == Qt.CheckState.Unchecked:
            # 显示消息，提示标签结果不会保存
            self.show_status("NOTE: Labels results are not saved.")

            # 将 YOLO 实例的保存标签的标志设置为 False
            self.yolo_predict.save_txt = False
        elif self.save_txt_button.checkState() == Qt.CheckState.Checked:
            # 显示消息，提示标签结果将会保存
            self.show_status("NOTE: Labels results will be saved.")

            # 将 YOLO 实例的保存标签的标志设置为 True
            self.yolo_predict.save_txt = True

    # 终止按钮及相关状态处理
    def stop(self):
        # 如果 YOLO 线程正在运行，则终止线程
        if self.yolo_thread.isRunning():
            self.yolo_thread.quit()  # 结束线程

        # 设置 YOLO 实例的终止标志为 True
        self.yolo_predict.stop_dtc = True

        # 恢复开始按钮的状态
        self.run_button.setChecked(False)

        # 启用保存按钮的使用权限
        if self.task == "Classify":
            self.save_res_button.setEnabled(False)
            self.save_txt_button.setEnabled(False)
        else:
            self.save_res_button.setEnabled(True)
            self.save_txt_button.setEnabled(True)

        # 清空预测结果显示区域的影象
        self.pre_video.clear()

        # 清空检测结果显示区域的影象
        self.res_video.clear()

        # 将进度条的值设置为0
        self.progress_bar.setValue(0)

        # 重置类别数量、目标数量和fps标签
        self.Class_num.setText("--")
        self.Target_num.setText("--")
        self.fps_label.setText("--")

    # 更改检测参数
    def change_val(self, x, flag):
        if flag == "iou_spinbox":
            # 如果是 iou_spinbox 的值发生变化，则改变 iou_slider 的值
            self.iou_slider.setValue(int(x * 100))

        elif flag == "iou_slider":
            # 如果是 iou_slider 的值发生变化，则改变 iou_spinbox 的值
            self.iou_spinbox.setValue(x / 100)
            # 显示消息，提示 IOU 阈值变化
            self.show_status("IOU Threshold: %s" % str(x / 100))
            # 设置 YOLO 实例的 IOU 阈值
            self.yolo_predict.iou_thres = x / 100

        elif flag == "conf_spinbox":
            # 如果是 conf_spinbox 的值发生变化，则改变 conf_slider 的值
            self.conf_slider.setValue(int(x * 100))

        elif flag == "conf_slider":
            # 如果是 conf_slider 的值发生变化，则改变 conf_spinbox 的值
            self.conf_spinbox.setValue(x / 100)
            # 显示消息，提示 Confidence 阈值变化
            self.show_status("Conf Threshold: %s" % str(x / 100))
            # 设置 YOLO 实例的 Confidence 阈值
            self.yolo_predict.conf_thres = x / 100

        elif flag == "speed_spinbox":
            # 如果是 speed_spinbox 的值发生变化，则改变 speed_slider 的值
            self.speed_slider.setValue(x)

        elif flag == "speed_slider":
            # 如果是 speed_slider 的值发生变化，则改变 speed_spinbox 的值
            self.speed_spinbox.setValue(x)
            # 显示消息，提示延迟时间变化
            self.show_status("Delay: %s ms" % str(x))
            # 设置 YOLO 实例的延迟时间阈值
            self.yolo_predict.speed_thres = x  # 毫秒

    # 更改模型
    def change_model(self, x):
        # 获取当前选择的模型名称
        self.select_model = self.model_box.currentText()

        # 设置 YOLO 实例的新模型名称
        if self.task == "Classify":
            self.yolo_predict.new_model_name = (
                "./models/classify/%s" % self.select_model
            )
        elif self.task == "Detect":
            self.yolo_predict.new_model_name = "./models/detect/%s" % self.select_model
        elif self.task == "Pose":
            self.yolo_predict.new_model_name = "./models/pose/%s" % self.select_model
        elif self.task == "Segment":
            self.yolo_predict.new_model_name = "./models/segment/%s" % self.select_model
        elif self.task == "Track":
            self.yolo_predict.new_model_name = "./models/track/%s" % self.select_model
        # 显示消息，提示模型已更改
        self.show_status("Change Model：%s" % self.select_model)

        # 在界面上显示新的模型名称
        self.Model_name.setText(self.select_model)

    ####################################image or video####################################

    ####################################camera####################################
    def cam_button(self):
        self.yolo_predict_cam.source = 0
        self.show_status("目前页面：Webcam检测页面")
        # 结束image or video线程，节省资源
        if self.yolo_thread.isRunning():
            self.yolo_thread.quit()  # 结束线程
            self.stop()

        if self.PageIndex != 2:
            self.PageIndex = 2
            self.content.setCurrentIndex(self.PageIndex)
            self.settings_button.clicked.connect(
                lambda: UIFuncitons.cam_settingBox(self, True)
            )  # 右上方设置按钮

    # cam控制开始/暂停检测
    def cam_run_or_continue(self):
        if self.yolo_predict_cam.source == "":
            self.show_status("并未检测到摄影机")
            self.run_button_cam.setChecked(False)

        else:
            # 设置 YOLO 预测的停止标志为 False
            self.yolo_predict_cam.stop_dtc = False

            # 如果开始按钮被勾选
            if self.run_button_cam.isChecked():
                self.run_button_cam.setChecked(True)  # 启动按钮
                self.save_txt_button_cam.setEnabled(False)  # 启动检测后禁止勾选保存
                self.save_res_button_cam.setEnabled(False)
                self.cam_show_status("检测中...")
                self.yolo_predict_cam.continue_dtc = True  # 控制 YOLO 是否暂停

                if not self.yolo_thread_cam.isRunning():
                    self.yolo_thread_cam.start()
                    self.main2yolo_begin_sgl.emit()

            # 如果开始按钮未被勾选，表示暂停检测
            else:
                self.yolo_predict_cam.continue_dtc = False
                self.cam_show_status("检测暂停...")
                self.run_button_cam.setChecked(False)  # 停止按钮

    # cam主视窗显示原始图片和检测结果
    @staticmethod
    def cam_show_image(img_src, label):
        try:
            # 获取原始图片的高度、宽度和通道数
            ih, iw, _ = img_src.shape

            # 获取标签(label)的宽度和高度
            w = label.geometry().width()
            h = label.geometry().height()

            # 保持原始数据比例
            if iw / w > ih / h:
                scal = w / iw
                nw = w
                nh = int(scal * ih)
                img_src_ = cv2.resize(img_src, (nw, nh))
            else:
                scal = h / ih
                nw = int(scal * iw)
                nh = h
                img_src_ = cv2.resize(img_src, (nw, nh))

            # 将图片转换为RGB格式
            frame = cv2.cvtColor(img_src_, cv2.COLOR_BGR2RGB)

            # 将图片数据转换为Qt的图片对象
            img = QImage(
                frame.data,
                frame.shape[1],
                frame.shape[0],
                frame.shape[2] * frame.shape[1],
                QImage.Format_RGB888,
            )

            # 将图片显示在标签(label)上
            label.setPixmap(QPixmap.fromImage(img))

        except Exception as e:
            # 处理异常，印出错误信息
            traceback.print_exc()
            print(f"Error: {e}")
            self.cam_show_status("%s" % e)

    # 更改检测参数
    def cam_change_val(self, c, flag):
        if flag == "iou_spinbox_cam":
            # 如果是 iou_spinbox 的值发生变化，则改变 iou_slider 的值
            self.iou_slider_cam.setValue(int(c * 100))

        elif flag == "iou_slider_cam":
            # 如果是 iou_slider 的值发生变化，则改变 iou_spinbox 的值
            self.iou_spinbox_cam.setValue(c / 100)
            # 显示消息，提示 IOU 阈值变化
            self.cam_show_status("IOU Threshold: %s" % str(c / 100))
            # 设置 YOLO 实例的 IOU 阈值
            self.yolo_predict_cam.iou_thres = c / 100

        elif flag == "conf_spinbox_cam":
            # 如果是 conf_spinbox 的值发生变化，则改变 conf_slider 的值
            self.conf_slider_cam.setValue(int(c * 100))

        elif flag == "conf_slider_cam":
            # 如果是 conf_slider 的值发生变化，则改变 conf_spinbox 的值
            self.conf_spinbox_cam.setValue(c / 100)
            # 显示消息，提示 Confidence 阈值变化
            self.cam_show_status("Conf Threshold: %s" % str(c / 100))
            # 设置 YOLO 实例的 Confidence 阈值
            self.yolo_predict_cam.conf_thres = c / 100

        elif flag == "speed_spinbox_cam":
            # 如果是 speed_spinbox 的值发生变化，则改变 speed_slider 的值
            self.speed_slider_cam.setValue(c)

        elif flag == "speed_slider_cam":
            # 如果是 speed_slider 的值发生变化，则改变 speed_spinbox 的值
            self.speed_spinbox_cam.setValue(c)
            # 显示消息，提示延迟时间变化
            self.cam_show_status("Delay: %s ms" % str(c))
            # 设置 YOLO 实例的延迟时间阈值
            self.yolo_predict_cam.speed_thres = c  # 毫秒

    # 更改模型
    def cam_change_model(self, c):
        # 获取当前选择的模型名称
        self.select_model_cam = self.model_box_cam.currentText()

        # 设置 YOLO 实例的新模型名称
        if self.task == "Classify":
            self.yolo_predict_cam.new_model_name = (
                "./models/classify/%s" % self.select_model_cam
            )
        elif self.task == "Detect":
            self.yolo_predict_cam.new_model_name = (
                "./models/detect/%s" % self.select_model_cam
            )
        elif self.task == "Pose":
            self.yolo_predict_cam.new_model_name = (
                "./models/pose/%s" % self.select_model_cam
            )
        elif self.task == "Segment":
            self.yolo_predict_cam.new_model_name = (
                "./models/segment/%s" % self.select_model_cam
            )
        elif self.task == "Track":
            self.yolo_predict_cam.new_model_name = (
                "./models/track/%s" % self.select_model_cam
            )
        # 显示消息，提示模型已更改
        self.cam_show_status("Change Model：%s" % self.select_model_cam)

        # 在界面上显示新的模型名称
        self.Model_name_cam.setText(self.select_model_cam)

    # 显示底部状态栏信息
    def cam_show_status(self, msg):
        # 设置状态栏文字
        self.status_bar.setText(msg)

        # 根据不同的状态信息执行相应的操作
        if msg == "Detection completed" or msg == "检测完成":
            # 启用保存结果和保存文本的按钮
            self.save_res_button_cam.setEnabled(True)
            self.save_txt_button_cam.setEnabled(True)

            # 将检测开关按钮设置为未勾选状态
            self.run_button_cam.setChecked(False)

            # 将进度条的值设置为0
            self.progress_bar_cam.setValue(0)

            # 如果 YOLO 线程正在运行，则终止该线程
            if self.yolo_thread_cam.isRunning():
                self.yolo_thread_cam.quit()  # 结束处理

        elif msg == "Detection terminated!" or msg == "检测终止":
            # 启用保存结果和保存文本的按钮
            self.save_res_button_cam.setEnabled(True)
            self.save_txt_button_cam.setEnabled(True)

            # 将检测开关按钮设置为未勾选状态
            self.run_button_cam.setChecked(False)

            # 将进度条的值设置为0
            self.progress_bar_cam.setValue(0)

            # 如果 YOLO 线程正在运行，则终止该线程
            if self.yolo_thread_cam.isRunning():
                self.yolo_thread_cam.quit()  # 结束处理

            # 清空影像显示
            self.pre_cam.clear()  # 清除原始图像
            self.res_cam.clear()  # 清除检测结果图像
            self.Class_num_cam.setText("--")  # 显示的类别数目
            self.Target_num_cam.setText("--")  # 显示的目标数目
            self.fps_label_cam.setText("--")  # 显示的帧率信息

    # 保存测试结果按钮 -- 图片/视频
    def cam_is_save_res(self):
        if self.save_res_button_cam.checkState() == Qt.CheckState.Unchecked:
            # 显示消息，提示运行图片结果不会保存
            self.show_status("NOTE：运行图片结果不会保存")

            # 将 YOLO 实例的保存结果的标志设置为 False
            self.yolo_thread_cam.save_res = False
        elif self.save_res_button_cam.checkState() == Qt.CheckState.Checked:
            # 显示消息，提示运行图片结果将会保存
            self.show_status("NOTE：运行图片结果将会保存")

            # 将 YOLO 实例的保存结果的标志设置为 True
            self.yolo_thread_cam.save_res = True

    # 保存测试结果按钮 -- 标签（txt）
    def cam_is_save_txt(self):
        if self.save_txt_button_cam.checkState() == Qt.CheckState.Unchecked:
            # 显示消息，提示标签结果不会保存
            self.show_status("NOTE：Label结果不会保存")

            # 将 YOLO 实例的保存标签的标志设置为 False
            self.yolo_thread_cam.save_txt_cam = False
        elif self.save_txt_button_cam.checkState() == Qt.CheckState.Checked:
            # 显示消息，提示标签结果将会保存
            self.show_status("NOTE：Label结果将会保存")

            # 将 YOLO 实例的保存标签的标志设置为 True
            self.yolo_thread_cam.save_txt_cam = True

    # cam终止按钮及相关状态处理
    def cam_stop(self):
        # 如果 YOLO 线程正在运行，则终止线程
        if self.yolo_thread_cam.isRunning():
            self.yolo_thread_cam.quit()  # 结束线程

        # 设置 YOLO 实例的终止标志为 True
        self.yolo_predict_cam.stop_dtc = True

        # 恢复开始按钮的状态
        self.run_button_cam.setChecked(False)

        # 启用保存按钮的使用权限
        if self.task == "Classify":
            self.save_res_button_cam.setEnabled(False)
            self.save_txt_button_cam.setEnabled(False)
        else:
            self.save_res_button_cam.setEnabled(True)
            self.save_txt_button_cam.setEnabled(True)

        # 清空预测结果显示区域的影象
        self.pre_cam.clear()

        # 清空检测结果显示区域的影象
        self.res_cam.clear()

        # 将进度条的值设置为0
        # self.progress_bar.setValue(0)

        # 重置类别数量、目标数量和fps标签
        self.Class_num_cam.setText("--")
        self.Target_num_cam.setText("--")
        self.fps_label_cam.setText("--")

    ####################################camera####################################

    ####################################共用####################################
    # 循环监控模型文件更改
    def ModelBoxRefre(self):
        # 获取模型文件夹下的所有模型文件
        if self.task == "Classify":
            pt_list = os.listdir("./models/classify")
            pt_list = [
                file for file in pt_list if file.endswith((".pt", "onnx", "engine"))
            ]
            pt_list.sort(key=lambda x: os.path.getsize("./models/classify/" + x))

            # 如果模型文件列表发生变化，则更新模型下拉框的内容
            if pt_list != self.pt_list:
                self.pt_list = pt_list
                self.model_box.clear()
                self.model_box.addItems(self.pt_list)
                self.pt_list_cam = pt_list
                self.model_box_cam.clear()
                self.model_box_cam.addItems(self.pt_list_cam)

        elif self.task == "Detect":
            pt_list = os.listdir("./models/detect")
            pt_list = [
                file for file in pt_list if file.endswith((".pt", "onnx", "engine"))
            ]
            pt_list.sort(key=lambda x: os.path.getsize("./models/detect/" + x))
            # 如果模型文件列表发生变化，则更新模型下拉框的内容
            if pt_list != self.pt_list:
                self.pt_list = pt_list
                self.model_box.clear()
                self.model_box.addItems(self.pt_list)
                self.pt_list_cam = pt_list
                self.model_box_cam.clear()
                self.model_box_cam.addItems(self.pt_list_cam)

        elif self.task == "Pose":
            pt_list = os.listdir("./models/pose")
            pt_list = [
                file for file in pt_list if file.endswith((".pt", "onnx", "engine"))
            ]
            pt_list.sort(key=lambda x: os.path.getsize("./models/pose/" + x))

            # 如果模型文件列表发生变化，则更新模型下拉框的内容
            if pt_list != self.pt_list:
                self.pt_list = pt_list
                self.model_box.clear()
                self.model_box.addItems(self.pt_list)
                self.pt_list_cam = pt_list
                self.model_box_cam.clear()
                self.model_box_cam.addItems(self.pt_list_cam)

        elif self.task == "Segment":
            pt_list = os.listdir("./models/segment")
            pt_list = [
                file for file in pt_list if file.endswith((".pt", "onnx", "engine"))
            ]
            pt_list.sort(key=lambda x: os.path.getsize("./models/segment/" + x))

            # 如果模型文件列表发生变化，则更新模型下拉框的内容
            if pt_list != self.pt_list:
                self.pt_list = pt_list
                self.model_box.clear()
                self.model_box.addItems(self.pt_list)
                self.pt_list_cam = pt_list
                self.model_box_cam.clear()
                self.model_box_cam.addItems(self.pt_list_cam)

        elif self.task == "Track":
            pt_list = os.listdir("./models/track")
            pt_list = [
                file for file in pt_list if file.endswith((".pt", "onnx", "engine"))
            ]
            pt_list.sort(key=lambda x: os.path.getsize("./models/track/" + x))

            # 如果模型文件列表发生变化，则更新模型下拉框的内容
            if pt_list != self.pt_list:
                self.pt_list = pt_list
                self.model_box.clear()
                self.model_box.addItems(self.pt_list)
                self.pt_list_cam = pt_list
                self.model_box_cam.clear()
                self.model_box_cam.addItems(self.pt_list_cam)

    # 获取滑鼠位置（用于按住标题栏拖动窗口）
    def mousePressEvent(self, event):
        p = event.globalPosition()
        globalPos = p.toPoint()
        self.dragPos = globalPos

    # 在调整窗口大小时进行优化调整（针对拖动窗口右下角边缘调整窗口大小）
    def resizeEvent(self, event):
        # 更新大小调整的手柄
        UIFuncitons.resize_grips(self)

    # 配置初始化
    def load_config(self):
        config_file = "config/setting.json"

        # 如果配置文件不存在，则创建并写入默认配置
        if not os.path.exists(config_file):
            iou = 0.26
            conf = 0.33
            rate = 10
            save_res = 0
            save_txt = 0
            save_res_cam = 0
            save_txt_cam = 0
            new_config = {
                "iou": iou,
                "conf": conf,
                "rate": rate,
                "save_res": save_res,
                "save_txt": save_txt,
                "save_res": save_res_cam,
                "save_txt": save_txt_cam,
            }
            new_json = json.dumps(new_config, ensure_ascii=False, indent=2)
            with open(config_file, "w", encoding="utf-8") as f:
                f.write(new_json)
        else:
            # 如果配置文件存在，读取配置
            config = json.load(open(config_file, "r", encoding="utf-8"))

            # 检查配置内容是否完整，如果不完整，使用默认值
            if len(config) != 7:
                iou = 0.26
                conf = 0.33
                rate = 10
                save_res = 0
                save_txt = 0
                save_res_cam = 0
                save_txt_cam = 0
            else:
                iou = config["iou"]
                conf = config["conf"]
                rate = config["rate"]
                save_res = config["save_res"]
                save_txt = config["save_txt"]
                save_res_cam = config["save_res_cam"]
                save_txt_cam = config["save_txt_cam"]

        # 根据配置设置界面元素的状态
        self.save_res_button.setCheckState(Qt.CheckState(save_res))
        self.yolo_predict.save_res = False if save_res == 0 else True
        self.save_txt_button.setCheckState(Qt.CheckState(save_txt))
        self.yolo_predict.save_txt = False if save_txt == 0 else True
        self.run_button.setChecked(False)

        self.save_res_button_cam.setCheckState(Qt.CheckState(save_res_cam))
        self.yolo_predict_cam.save_res_cam = False if save_res_cam == 0 else True
        self.save_txt_button_cam.setCheckState(Qt.CheckState(save_txt_cam))
        self.yolo_predict_cam.save_txt_cam = False if save_txt_cam == 0 else True
        self.run_button_cam.setChecked(False)
        self.show_status("欢迎使用YOLOv8检测系统，请选择Mode")
        # self.show_status("目前为image or video检测页面")

    # 关闭事件，退出线程，保存设置
    def closeEvent(self, event):
        # 保存配置到设定文件
        config_file = "config/setting.json"
        config = dict()
        config["iou"] = self.iou_spinbox.value()
        config["conf"] = self.conf_spinbox.value()
        config["rate"] = self.speed_spinbox.value()
        config["save_res"] = (
            0 if self.save_res_button.checkState() == Qt.Unchecked else 2
        )
        config["save_txt"] = (
            0 if self.save_txt_button.checkState() == Qt.Unchecked else 2
        )
        config["save_res_cam"] = (
            0 if self.save_res_button_cam.checkState() == Qt.Unchecked else 2
        )
        config["save_txt_cam"] = (
            0 if self.save_txt_button_cam.checkState() == Qt.Unchecked else 2
        )
        config_json = json.dumps(config, ensure_ascii=False, indent=2)
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(config_json)

        # 退出线程和应用程序
        if self.yolo_thread.isRunning() or self.yolo_thread_cam.isRunning():
            # 如果 YOLO 线程正在运行，则终止线程
            self.yolo_predict.stop_dtc = True
            self.yolo_thread.quit()

            self.yolo_predict_cam.stop_dtc = True
            self.yolo_thread_cam.quit()
            # 显示退出提示，等待3秒
            MessageBox(
                self.close_button,
                title="Note",
                text="Exiting, please wait...",
                time=3000,
                auto=True,
            ).exec()

            # 退出应用程序
            sys.exit(0)
        else:
            # 如果 YOLO 线程未运行，直接退出应用程序
            sys.exit(0)

    ####################################共用####################################


if __name__ == "__main__":
    app = QApplication(sys.argv)
    Home = MainWindow()
    # 创建相机线程
    # camera_thread = CameraThread()
    # camera_thread.imageCaptured.connect(Home.cam_data)
    # camera_thread.start()
    Home.show()
    sys.exit(app.exec())
