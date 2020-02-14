from fbs_runtime.application_context.PyQt5 import ApplicationContext
from PyQt5.QtWidgets import QMainWindow
import sys

# !/usr/bin/python3
# Video Annotation tool implemented with PyQt5
# features: open/play video and its scripts and annotated segments.

from PyQt5.QtCore import (pyqtSignal, pyqtSlot, Q_ARG, QAbstractItemModel,
                          QFileInfo, qFuzzyCompare, QMetaObject, QModelIndex, QObject, Qt,
                          QThread, QTime, QUrl)
from PyQt5.QtGui import QColor, qGray, QImage, QPainter, QPalette
from PyQt5.QtMultimedia import (QAbstractVideoBuffer, QMediaContent,
                                QMediaMetaData, QMediaPlayer, QMediaPlaylist, QVideoFrame, QVideoProbe)
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtWidgets import (QApplication, QComboBox, QDialog, QFileDialog,
                             QFormLayout, QHBoxLayout, QLabel, QListView, QMessageBox, QPushButton,
                             QSizePolicy, QSlider, QStyle, QToolButton, QVBoxLayout, QWidget, QPlainTextEdit,
                             QTreeWidget, QTreeWidgetItem, QLineEdit, QMenu)
import os

import math

SEGMENT_DIR = './segments/'
VIDEO_DIR = './videos/'


# SCRIPT_DIR = './scripts/'

class TreeWidgetItem(QTreeWidgetItem):
    def __init__(self, parent=None):
        QTreeWidgetItem.__init__(self, parent)

    def __lt__(self, otherItem):
        column = self.treeWidget().sortColumn()
        try:
            return float(self.text(column)) < float(otherItem.text(column))
        except ValueError:
            return self.text(column) < otherItem.text(column)


class VideoWidget(QVideoWidget):

    def __init__(self, parent=None):
        super(VideoWidget, self).__init__(parent)

        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)

        p = self.palette()
        p.setColor(QPalette.Window, Qt.black)
        self.setPalette(p)

        self.setAttribute(Qt.WA_OpaquePaintEvent)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self.isFullScreen():
            self.setFullScreen(False)
            event.accept()
        elif event.key() == Qt.Key_Enter and event.modifiers() & Qt.Key_Alt:
            self.setFullScreen(not self.isFullScreen())
            event.accept()
        else:
            super(VideoWidget, self).keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.setFullScreen(not self.isFullScreen())
        event.accept()


class PlaylistModel(QAbstractItemModel):
    Title, ColumnCount = range(2)

    def __init__(self, parent=None):
        super(PlaylistModel, self).__init__(parent)

        self.m_playlist = None

    def rowCount(self, parent=QModelIndex()):
        return self.m_playlist.mediaCount() if self.m_playlist is not None and not parent.isValid() else 0

    def columnCount(self, parent=QModelIndex()):
        return self.ColumnCount if not parent.isValid() else 0

    def index(self, row, column, parent=QModelIndex()):
        return self.createIndex(row,
                                column) if self.m_playlist is not None and not parent.isValid() and row >= 0 and row < self.m_playlist.mediaCount() and column >= 0 and column < self.ColumnCount else QModelIndex()

    def parent(self, child):
        return QModelIndex()

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid() and role == Qt.DisplayRole:
            if index.column() == self.Title:
                location = self.m_playlist.media(index.row()).canonicalUrl()
                return QFileInfo(location.path()).fileName()

            return self.m_data[index]

        return None

    def playlist(self):
        return self.m_playlist

    def setPlaylist(self, playlist):
        if self.m_playlist is not None:
            self.m_playlist.mediaAboutToBeInserted.disconnect(
                self.beginInsertItems)
            self.m_playlist.mediaInserted.disconnect(self.endInsertItems)
            self.m_playlist.mediaAboutToBeRemoved.disconnect(
                self.beginRemoveItems)
            self.m_playlist.mediaRemoved.disconnect(self.endRemoveItems)
            self.m_playlist.mediaChanged.disconnect(self.changeItems)

        self.beginResetModel()
        self.m_playlist = playlist

        if self.m_playlist is not None:
            self.m_playlist.mediaAboutToBeInserted.connect(
                self.beginInsertItems)
            self.m_playlist.mediaInserted.connect(self.endInsertItems)
            self.m_playlist.mediaAboutToBeRemoved.connect(
                self.beginRemoveItems)
            self.m_playlist.mediaRemoved.connect(self.endRemoveItems)
            self.m_playlist.mediaChanged.connect(self.changeItems)

        self.endResetModel()

    def beginInsertItems(self, start, end):
        self.beginInsertRows(QModelIndex(), start, end)

    def endInsertItems(self):
        self.endInsertRows()

    def beginRemoveItems(self, start, end):
        self.beginRemoveRows(QModelIndex(), start, end)

    def endRemoveItems(self):
        self.endRemoveRows()

    def changeItems(self, start, end):
        self.dataChanged.emit(self.index(start, 0),
                              self.index(end, self.ColumnCount))


class PlayerControls(QWidget):
    play = pyqtSignal()
    pause = pyqtSignal()
    stop = pyqtSignal()
    nextjump5 = pyqtSignal()
    previousjump5 = pyqtSignal()
    nextjump10 = pyqtSignal()
    previousjump10 = pyqtSignal()
    nextjump60 = pyqtSignal()
    previousjump60 = pyqtSignal()
    changeVolume = pyqtSignal(int)
    changeMuting = pyqtSignal(bool)
    changeRate = pyqtSignal(float)

    def __init__(self, parent=None):
        super(PlayerControls, self).__init__(parent)
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        self.playerState = QMediaPlayer.StoppedState
        self.playerMuted = False
        self.playButton = QToolButton(clicked=self.playClicked)
        self.playButton.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.stopButton = QToolButton(clicked=self.stop)
        self.stopButton.setIcon(self.style().standardIcon(QStyle.SP_MediaStop))
        self.stopButton.setEnabled(False)

        self.nextJump5Button = QToolButton(clicked=self.nextjump5)
        self.nextJump5Button.setText('+5')

        self.previousJump5Button = QToolButton(clicked=self.previousjump5)
        self.previousJump5Button.setText('-5')

        self.nextJump10Button = QToolButton(clicked=self.nextjump10)
        self.nextJump10Button.setText('+10')

        self.previousJump10Button = QToolButton(clicked=self.previousjump10)
        self.previousJump10Button.setText('-10')

        self.nextJump60Button = QToolButton(clicked=self.nextjump60)
        self.nextJump60Button.setText('+60')

        self.previousJump60Button = QToolButton(clicked=self.previousjump60)
        self.previousJump60Button.setText('-60')


        self.muteButton = QToolButton(clicked=self.muteClicked)
        self.muteButton.setIcon(
            self.style().standardIcon(QStyle.SP_MediaVolume))

        self.volumeSlider = QSlider(Qt.Horizontal,
                                    sliderMoved=self.changeVolume)
        self.volumeSlider.setRange(0, 100)

        self.rateBox = QComboBox(activated=self.updateRate)
        self.rateBox.addItem("0.5x", 0.5)
        self.rateBox.addItem("1.0x", 1.0)
        self.rateBox.addItem("2.0x", 2.0)
        self.rateBox.addItem("4.0x", 4.0)

        self.rateBox.setCurrentIndex(1)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stopButton)
        layout.addWidget(self.previousJump60Button)
        layout.addWidget(self.previousJump10Button)
        layout.addWidget(self.previousJump5Button)
        layout.addWidget(self.playButton)
        layout.addWidget(self.nextJump5Button)
        layout.addWidget(self.nextJump10Button)
        layout.addWidget(self.nextJump60Button)
        layout.addWidget(self.muteButton)
        layout.addWidget(self.volumeSlider)
        layout.addWidget(self.rateBox)
        self.setLayout(layout)

    def state(self):
        return self.playerState

    def setState(self, state):
        if state != self.playerState:
            self.playerState = state

            if state == QMediaPlayer.StoppedState:
                self.stopButton.setEnabled(False)
                self.playButton.setIcon(
                    self.style().standardIcon(QStyle.SP_MediaPlay))
            elif state == QMediaPlayer.PlayingState:
                self.stopButton.setEnabled(True)
                self.playButton.setIcon(
                    self.style().standardIcon(QStyle.SP_MediaPause))
            elif state == QMediaPlayer.PausedState:
                self.stopButton.setEnabled(True)
                self.playButton.setIcon(
                    self.style().standardIcon(QStyle.SP_MediaPlay))

    def volume(self):
        return self.volumeSlider.value()

    def setVolume(self, volume):
        self.volumeSlider.setValue(volume)

    def isMuted(self):
        return self.playerMuted

    def setMuted(self, muted):
        if muted != self.playerMuted:
            self.playerMuted = muted

            self.muteButton.setIcon(
                self.style().standardIcon(
                    QStyle.SP_MediaVolumeMuted if muted else QStyle.SP_MediaVolume))

    def playClicked(self):
        if self.playerState in (QMediaPlayer.StoppedState, QMediaPlayer.PausedState):
            self.play.emit()
        elif self.playerState == QMediaPlayer.PlayingState:
            self.pause.emit()

    def muteClicked(self):
        self.changeMuting.emit(not self.playerMuted)

    def playbackRate(self):
        return self.rateBox.itemData(self.rateBox.currentIndex())
    #
    # def setPlaybackRate(self, rate):
    #     for i in range(self.rateBox.count()):
    #         if qFuzzyCompare(rate, self.rateBox.itemData(i)):
    #             self.rateBox.setCurrentIndex(i)
    #             return
    #
    #     self.rateBox.addItem("%dx" % rate, rate)
    #     self.rateBox.setCurrentIndex(self.rateBox.count() - 1)

    def updateRate(self):
        self.changeRate.emit(self.playbackRate())


class FrameProcessor(QObject):
    histogramReady = pyqtSignal(list)

    @pyqtSlot(QVideoFrame, int)
    def processFrame(self, frame, levels):
        histogram = [0.0] * levels

        if levels and frame.map(QAbstractVideoBuffer.ReadOnly):
            pixelFormat = frame.pixelFormat()

            if pixelFormat == QVideoFrame.Format_YUV420P or pixelFormat == QVideoFrame.Format_NV12:
                # Process YUV data.
                bits = frame.bits()
                for idx in range(frame.height() * frame.width()):
                    histogram[(bits[idx] * levels) >> 8] += 1.0
            else:
                imageFormat = QVideoFrame.imageFormatFromPixelFormat(pixelFormat)
                if imageFormat != QImage.Format_Invalid:
                    # Process RGB data.
                    image = QImage(frame.bits(), frame.width(), frame.height(), imageFormat)

                    for y in range(image.height()):
                        for x in range(image.width()):
                            pixel = image.pixel(x, y)
                            histogram[(qGray(pixel) * levels) >> 8] += 1.0

            # Find the maximum value.
            maxValue = 0.0
            for value in histogram:
                if value > maxValue:
                    maxValue = value

            # Normalise the values between 0 and 1.
            if maxValue > 0.0:
                for i in range(len(histogram)):
                    histogram[i] /= maxValue

            frame.unmap()

        self.histogramReady.emit(histogram)


class HistogramWidget(QWidget):

    def __init__(self, parent=None):
        super(HistogramWidget, self).__init__(parent)

        self.m_levels = 128
        self.m_isBusy = False
        self.m_histogram = []
        self.m_processor = FrameProcessor()
        self.m_processorThread = QThread()

        self.m_processor.moveToThread(self.m_processorThread)
        self.m_processor.histogramReady.connect(self.setHistogram)

    def __del__(self):
        self.m_processorThread.quit()
        self.m_processorThread.wait(10000)

    def setLevels(self, levels):
        self.m_levels = levels

    def processFrame(self, frame):
        if self.m_isBusy:
            return

        self.m_isBusy = True
        QMetaObject.invokeMethod(self.m_processor, 'processFrame',
                                 Qt.QueuedConnection, Q_ARG(QVideoFrame, frame),
                                 Q_ARG(int, self.m_levels))

    @pyqtSlot(list)
    def setHistogram(self, histogram):
        self.m_isBusy = False
        self.m_histogram = list(histogram)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)

        if len(self.m_histogram) == 0:
            painter.fillRect(0, 0, self.width(), self.height(),
                             QColor.fromRgb(0, 0, 0))
            return

        barWidth = self.width() / float(len(self.m_histogram))

        for i, value in enumerate(self.m_histogram):
            h = value * self.height()
            # Draw the level.
            painter.fillRect(barWidth * i, self.height() - h,
                             barWidth * (i + 1), self.height(), Qt.red)
            # Clear the rest of the control.
            painter.fillRect(barWidth * i, 0, barWidth * (i + 1),
                             self.height() - h, Qt.black)


class Player(QWidget):
    fullScreenChanged = pyqtSignal(bool)

    def __init__(self, playlist, parent=None):
        super(Player, self).__init__(parent)
        self.colorDialog = None
        self.trackInfo = ""
        self.statusInfo = ""
        self.duration = 0

        self.player = QMediaPlayer()
        self.playlist = QMediaPlaylist()
        self.player.setPlaylist(self.playlist)

        self.player.durationChanged.connect(self.durationChanged)
        self.player.positionChanged.connect(self.positionChanged)
        self.player.metaDataChanged.connect(self.metaDataChanged)
        self.playlist.currentIndexChanged.connect(self.playlistPositionChanged)
        self.player.mediaStatusChanged.connect(self.statusChanged)
        self.player.bufferStatusChanged.connect(self.bufferingProgress)
        self.player.videoAvailableChanged.connect(self.videoAvailableChanged)
        self.player.error.connect(self.displayErrorMessage)

        self.videoWidget = VideoWidget()
        self.player.setVideoOutput(self.videoWidget)

        self.playlistModel = PlaylistModel()
        self.playlistModel.setPlaylist(self.playlist)

        self.playlistView = QListView()
        self.playlistView.setModel(self.playlistModel)
        self.playlistView.setCurrentIndex(
            self.playlistModel.index(self.playlist.currentIndex(), 0))

        self.playlistView.activated.connect(self.jump)

        self.script_box = QPlainTextEdit()
        self.segmentList = QTreeWidget()
        self.segmentList.setSortingEnabled(True)
        # self.segmentList.setColumnCount(5)
        self.segmentList.setColumnCount(4)
        # self.segmentList.setHeaderLabels(['Product','Start','Label','Tool','Behavior'])
        self.segmentList.setHeaderLabels(['Start segment', 'End segment', 'Label', 'Event'])

        '''
        self.productTextInput = QLineEdit()
        self.startTextInput = QLineEdit()
        self.labelTextInput = QLineEdit()
        self.toolTextInput = QLineEdit()
        self.behaviorTextInput = QLineEdit()
        '''
        self.startTextInput = QLineEdit()
        self.endTextInput = QLineEdit()
        self.labelTextInput = QLineEdit()
        self.eventTextInput = QLineEdit()

        self.addBtn = QPushButton("Add")
        self.addBtn.clicked.connect(self.addSegment)

        self.saveBtn = QPushButton("Save")
        self.saveBtn.clicked.connect(self.saveSegments)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, self.player.duration() / 1000)

        self.labelDuration = QLabel()
        self.slider.sliderMoved.connect(self.seek)

        self.labelHistogram = QLabel()
        self.labelHistogram.setText("Histogram:")
        self.histogram = HistogramWidget()
        histogramLayout = QHBoxLayout()
        histogramLayout.addWidget(self.labelHistogram)
        histogramLayout.addWidget(self.histogram, 1)

        self.probe = QVideoProbe()
        self.probe.videoFrameProbed.connect(self.histogram.processFrame)
        self.probe.setSource(self.player)

        openButton = QPushButton("Open", clicked=self.open)
        if os.path.isdir(VIDEO_DIR):
            self.open_folder(VIDEO_DIR)

        controls = PlayerControls()
        controls.setState(self.player.state())
        controls.setVolume(self.player.volume())
        controls.setMuted(controls.isMuted())

        controls.play.connect(self.player.play)
        controls.pause.connect(self.player.pause)
        controls.stop.connect(self.player.stop)
        controls.nextjump5.connect(self.nextJump5Clicked)
        controls.previousjump5.connect(self.previousJump5Clicked)
        controls.nextjump10.connect(self.nextJump10Clicked)
        controls.previousjump10.connect(self.previousJump10Clicked)
        controls.nextjump60.connect(self.nextJump60Clicked)
        controls.previousjump60.connect(self.previousJump60Clicked)

        controls.changeVolume.connect(self.player.setVolume)
        controls.changeMuting.connect(self.player.setMuted)
        controls.changeRate.connect(self.player.setPlaybackRate)
        controls.stop.connect(self.videoWidget.update)

        self.player.stateChanged.connect(controls.setState)
        self.player.volumeChanged.connect(controls.setVolume)
        self.player.mutedChanged.connect(controls.setMuted)

        # self.segmentButton = QPushButton("Segment")
        # self.segmentButton.clicked.connect(self.createNewSegment)
        self.startSegmentButton = QPushButton("Start Segment")
        self.startSegmentButton.clicked.connect(self.createNewStartSegment)
        # self.segmentButton.setCheckable(True)

        self.endSegmentButton = QPushButton("End Segment")
        self.endSegmentButton.clicked.connect(self.createNewEndSegment)

        # self.fullScreenButton = QPushButton("FullScreen")
        # self.fullScreenButton.setCheckable(True)

        self.colorButton = QPushButton("Color Options...")
        self.colorButton.setEnabled(False)
        self.colorButton.clicked.connect(self.showColorDialog)

        displayLayout = QHBoxLayout()
        # videoLayout = QVBoxLayout()
        # videoLayout.addWidget(self.videoWidget)
        # videoLayout.addWidget(self.script_box)

        displayLayout.addWidget(self.videoWidget, 3)

        editLayout = QVBoxLayout()
        editLayout.addWidget(self.playlistView, 2)
        # editLayout.addWidget(self.script_box, 4)
        editLayout.addWidget(self.segmentList, 3)
        segmentInputLayout = QHBoxLayout()
        '''
        segmentInputLayout.addWidget(self.productTextInput)
        segmentInputLayout.addWidget(self.startTextInput)
        segmentInputLayout.addWidget(self.labelTextInput)
        segmentInputLayout.addWidget(self.toolTextInput)
        segmentInputLayout.addWidget(self.behaviorTextInput)
        '''
        segmentInputLayout.addWidget(self.startTextInput)
        segmentInputLayout.addWidget(self.endTextInput)
        segmentInputLayout.addWidget(self.labelTextInput)
        segmentInputLayout.addWidget(self.eventTextInput)

        editLayout.addLayout(segmentInputLayout, 1)

        displayLayout.addLayout(editLayout, 2)

        controlLayout = QHBoxLayout()
        controlLayout.setContentsMargins(0, 0, 0, 0)
        controlLayout.addWidget(openButton)
        controlLayout.addStretch(1)
        controlLayout.addWidget(controls)
        controlLayout.addStretch(1)
        # controlLayout.addWidget(self.segmentButton)
        controlLayout.addWidget(self.startSegmentButton)
        controlLayout.addWidget(self.endSegmentButton)
        controlLayout.addWidget(self.addBtn)
        controlLayout.addWidget(self.saveBtn)
        # controlLayout.addWidget(self.fullScreenButton)
        # controlLayout.addWidget(self.colorButton)

        layout = QVBoxLayout()
        layout.addLayout(displayLayout, 2)
        hLayout = QHBoxLayout()
        hLayout.addWidget(self.slider)
        hLayout.addWidget(self.labelDuration)
        layout.addLayout(hLayout)
        layout.addLayout(controlLayout)
        # layout.addLayout(histogramLayout)

        self.setLayout(layout)

        if not self.player.isAvailable():
            QMessageBox.warning(self, "Service not available",
                                "The QMediaPlayer object does not have a valid service.\n"
                                "Please check the media service plugins are installed.")

            controls.setEnabled(False)
            self.playlistView.setEnabled(False)
            openButton.setEnabled(False)
            self.colorButton.setEnabled(False)
            # self.fullScreenButton.setEnabled(False)

        self.metaDataChanged()

        self.addToPlaylist(playlist)

    def open(self):
        fileNames, _ = QFileDialog.getOpenFileNames(self, "Open Files")
        self.addToPlaylist(fileNames)

    def open_folder(self, folder_path):
        fileNames = [folder_path + x for x in os.listdir(folder_path) if x.endswith('.mp4')]
        self.addToPlaylist(fileNames)

    def addToPlaylist(self, fileNames):
        for name in fileNames:
            fileInfo = QFileInfo(name)
            if fileInfo.exists():
                url = QUrl.fromLocalFile(fileInfo.absoluteFilePath())
                if fileInfo.suffix().lower() == 'm3u':
                    self.playlist.load(url)
                else:
                    self.playlist.addMedia(QMediaContent(url))
            else:
                url = QUrl(name)
                if url.isValid():
                    self.playlist.addMedia(QMediaContent(url))
            try:
                segment_file_path = SEGMENT_DIR + name.replace('.mp4', '.json')
                json_dict = self.open_json(segment_file_path)
                self.clear_input_boxes()
                self.segmentList.clear()
                for segment in json_dict["segments"]:
                    item = TreeWidgetItem(self.segmentList)
                    '''
                    item.setText(0, segment['product'])
                    item.setText(1, str(segment['start']))
                    item.setText(2, segment['label'])
                    item.setText(3, segment['tool'])
                    item.setText(4, segment['behavior'])
                    '''
                    item.setText(0, segment['start_segment'])
                    item.setText(1, segment['end_segment'])
                    item.setText(2, segment['label'])
                    item.setText(3, segment['event'])

                    item.setFlags(item.flags() | Qt.ItemIsEditable)
                    self.segmentList.addTopLevelItem(item)
            except:
                pass

    def addSegment(self):
        item = TreeWidgetItem(self.segmentList)
        '''
        item.setText(0, self.productTextInput.text())
        item.setText(1, self.startTextInput.text())
        item.setText(2, self.labelTextInput.text())
        item.setText(3, self.toolTextInput.text())
        item.setText(4, self.behaviorTextInput.text())
        '''

        item.setText(0, self.startTextInput.text())
        item.setText(1, self.endTextInput.text())
        item.setText(2, self.labelTextInput.text())
        item.setText(3, self.eventTextInput.text())

        item.setFlags(item.flags() | Qt.ItemIsEditable)
        self.segmentList.addTopLevelItem(item)
        self.segmentList.sortByColumn(0, Qt.AscendingOrder)

        self.clear_input_boxes()
        self.saveSegments()
        self.player.play()

    def saveSegments(self):
        itemCnt = self.segmentList.topLevelItemCount()
        colCnt = self.segmentList.columnCount()
        save_dict = {'segments': []}

        for i in range(itemCnt):
            item = self.segmentList.topLevelItem(i)
            temp_data = []
            for j in range(colCnt):
                temp_data.append(item.text(j))
            # temp_dict = {'product': temp_data[0], 'start': temp_data[1], 'label': temp_data[2], 'tool': temp_data[3], 'behavior': temp_data[4]}
            #
            # if len(temp_data[0]) > 0 and len(temp_data[1]) > 0 and (':' in temp_data[0]) and (':' in temp_data[1]):
            #
            #     start_interval_seconds = 0
            #     j = 0
            #     while j < len(temp_data[0].split(':')):
            #         start_interval_seconds += (int(temp_data[0].split(':')[- 1 - j]) * (60 ** j))
            #         j += 1
            #
            #     end_interval_seconds = 0
            #     j = 0
            #     while j < len(temp_data[1].split(':')):
            #         end_interval_seconds += (int(temp_data[1].split(':')[- 1 - j]) * (60 ** j))
            #         j += 1
            #
            # else:
            #     start_interval_seconds = ''
            #     end_interval_seconds = ''
            #
            # temp_dict = {'start_segment': start_interval_seconds, 'end_segment': end_interval_seconds,
            #              'label': temp_data[2], 'event': temp_data[3]}
            temp_dict = {'start_segment': temp_data[0], 'end_segment': temp_data[1],
                         'label': temp_data[2], 'event': temp_data[3]}
            save_dict['segments'].append(temp_dict)

        import json
        file_name = self.playlist.currentMedia().canonicalUrl().fileName()
        json_file = SEGMENT_DIR + file_name.replace('.mp4', '.json')
        # try:
        #     with open(json_file, 'r') as file:
        #         json_dict = json.loads(file.read())
        #         print(save_dict, json_dict)
        #         save_dict['segments'] = json_dict['segments'] + save_dict['segments']
        #         file.close()
        # except:
        #     pass

        with open(json_file, 'w') as file:
            json.dump(save_dict, file)

    def durationChanged(self, duration):
        duration /= 1000

        self.duration = duration
        self.slider.setMaximum(duration)

    def positionChanged(self, progress):
        progress /= 1000

        if not self.slider.isSliderDown():
            self.slider.setValue(progress)

        self.updateDurationInfo(progress)

    def metaDataChanged(self):
        if self.player.isMetaDataAvailable():
            self.setTrackInfo("%s - %s" % (
                self.player.metaData(QMediaMetaData.AlbumArtist),
                self.player.metaData(QMediaMetaData.Title)))

    def previousClicked(self):
        # Go to the previous track if we are within the first 5 seconds of
        # playback.  Otherwise, seek to the beginning.
        if self.player.position() <= 5000:
            self.playlist.previous()
        else:
            self.player.setPosition(0)
    def previousJump5Clicked(self):
        # Go to the previous track if we are within the first 5 seconds of
        # playback.  Otherwise, seek to the beginning.
        if self.player.position() < 5000:
            self.player.setPosition(0)
        else:
            self.player.setPosition(self.player.position() - 5000)

    def nextJump5Clicked(self):
        # Go to the previous track if we are within the first 5 seconds of
        # playback.  Otherwise, seek to the beginning.
        self.player.setPosition(self.player.position() + 5000)

    def previousJump10Clicked(self):
        # Go to the previous track if we are within the first 5 seconds of
        # playback.  Otherwise, seek to the beginning.
        if self.player.position() < 10000:
            self.player.setPosition(0)
        else:
            self.player.setPosition(self.player.position() - 10000)

    def nextJump10Clicked(self):
        # Go to the previous track if we are within the first 5 seconds of
        # playback.  Otherwise, seek to the beginning.
        self.player.setPosition(self.player.position() + 10000)

    def previousJump60Clicked(self):
        # Go to the previous track if we are within the first 5 seconds of
        # playback.  Otherwise, seek to the beginning.
        if self.player.position() < 60000:
            self.player.setPosition(0)
        else:
            self.player.setPosition(self.player.position() - 60000)

    def nextJump60Clicked(self):
        # Go to the previous track if we are within the first 5 seconds of
        # playback.  Otherwise, seek to the beginning.
        self.player.setPosition(self.player.position() + 60000)

    def clear_input_boxes(self):
        '''
        self.productTextInput.clear()
        self.startTextInput.clear()
        self.labelTextInput.clear()
        self.toolTextInput.clear()
        self.behaviorTextInput.clear()
        '''
        self.startTextInput.clear()
        self.endTextInput.clear()
        self.labelTextInput.clear()
        self.eventTextInput.clear()

    def jump(self, index):
        if index.isValid():
            self.playlist.setCurrentIndex(index.row())
            self.player.play()
            file_name = self.playlist.currentMedia().canonicalUrl().fileName()
            '''
            script_file_name = file_name.replace('.mp4','.txt')
            if os.path.isfile(SCRIPT_DIR+script_file_name):
                text=open(SCRIPT_DIR+script_file_name).read()
                self.script_box.setPlainText(text)
            '''

            segment_file_path = SEGMENT_DIR + file_name.replace('.mp4', '.json')
            json_dict = self.open_json(segment_file_path)
            self.clear_input_boxes()
            self.segmentList.clear()
            for segment in json_dict["segments"]:
                item = TreeWidgetItem(self.segmentList)
                '''
                item.setText(0, segment['product'])
                item.setText(1, str(segment['start']))
                item.setText(2, segment['label'])
                item.setText(3, segment['tool'])
                item.setText(4, segment['behavior'])
                '''
                item.setText(0, segment['start_segment'])
                item.setText(1, segment['end_segment'])
                item.setText(2, segment['label'])
                item.setText(3, segment['event'])

                item.setFlags(item.flags() | Qt.ItemIsEditable)
                self.segmentList.addTopLevelItem(item)

            # print([str(x.text()) for x in self.segmentList.currentItem()])

    def open_json(self, file_path):
        import json
        try:
            with open(file_path, 'r') as file:
                json_dict = json.loads(file.read())
        except:
            json_dict = {"segments": []}
            # json_dict = {"segments":[{"product":"Sorry","start":"File not found.","label":"","tool":"","behavior":""}]}
        return json_dict

    def playlistPositionChanged(self, position):
        self.playlistView.setCurrentIndex(
            self.playlistModel.index(position, 0))

    def seek(self, seconds):
        self.player.setPosition(seconds * 1000)

    def statusChanged(self, status):
        self.handleCursor(status)

        if status == QMediaPlayer.LoadingMedia:
            self.setStatusInfo("Loading...")
        elif status == QMediaPlayer.StalledMedia:
            self.setStatusInfo("Media Stalled")
        elif status == QMediaPlayer.EndOfMedia:
            QApplication.alert(self)
        elif status == QMediaPlayer.InvalidMedia:
            self.displayErrorMessage()
        else:
            self.setStatusInfo("")

    def handleCursor(self, status):
        if status in (QMediaPlayer.LoadingMedia, QMediaPlayer.BufferingMedia, QMediaPlayer.StalledMedia):
            self.setCursor(Qt.BusyCursor)
        else:
            self.unsetCursor()

    def bufferingProgress(self, progress):
        self.setStatusInfo("Buffering %d%" % progress)

    def videoAvailableChanged(self, available):
        '''
        if available:
            self.fullScreenButton.clicked.connect(
                    self.videoWidget.setFullScreen)
            self.videoWidget.fullScreenChanged.connect(
                    self.fullScreenButton.setChecked)

            if self.fullScreenButton.isChecked():
                self.videoWidget.setFullScreen(True)
        else:
            self.fullScreenButton.clicked.disconnect(
                    self.videoWidget.setFullScreen)
            self.videoWidget.fullScreenChanged.disconnect(
                    self.fullScreenButton.setChecked)

            self.videoWidget.setFullScreen(False)

        '''
        self.colorButton.setEnabled(available)

    def setTrackInfo(self, info):
        self.trackInfo = info

        if self.statusInfo != "":
            self.setWindowTitle("%s | %s" % (self.trackInfo, self.statusInfo))
        else:
            self.setWindowTitle(self.trackInfo)

    def setStatusInfo(self, info):
        self.statusInfo = info

        if self.statusInfo != "":
            self.setWindowTitle("%s | %s" % (self.trackInfo, self.statusInfo))
        else:
            self.setWindowTitle(self.trackInfo)

    def displayErrorMessage(self):
        self.setStatusInfo(self.player.errorString())

    def updateDurationInfo(self, currentInfo):
        duration = self.duration
        if currentInfo or duration:
            currentTime = QTime((currentInfo / 3600) % 60, (currentInfo / 60) % 60,
                                currentInfo % 60, (currentInfo * 1000) % 1000)
            totalTime = QTime((duration / 3600) % 60, (duration / 60) % 60,
                              duration % 60, (duration * 1000) % 1000);

            format = 'hh:mm:ss' if duration > 3600 else 'mm:ss'
            tStr = currentTime.toString(format) + " / " + totalTime.toString(format)
        else:
            tStr = ""

        self.labelDuration.setText(tStr)

    '''
    def createNewSegment(self):
        self.startTextInput.setText(str(int(self.player.position()/1000)))
    '''

    def createNewStartSegment(self):
        seconds = int(self.player.position() / 1000)
        self.startTextInput.setText("{:02d}".format(math.floor(seconds / 3600)) + ':' + "{:02d}".format(
            math.floor((seconds / 60)) - math.floor(seconds / 3600) * 60) + ':' + "{:02d}".format(seconds % 60))

    def createNewEndSegment(self):
        seconds = int(self.player.position() / 1000)
        self.endTextInput.setText("{:02d}".format(math.floor(seconds / 3600)) + ':' + "{:02d}".format(
            math.floor((seconds / 60)) - math.floor(seconds / 3600) * 60) + ':' + "{:02d}".format(seconds % 60))
        self.player.pause()

    def showColorDialog(self):
        if self.colorDialog is None:
            brightnessSlider = QSlider(Qt.Horizontal)
            brightnessSlider.setRange(-100, 100)
            brightnessSlider.setValue(self.videoWidget.brightness())
            brightnessSlider.sliderMoved.connect(
                self.videoWidget.setBrightness)
            self.videoWidget.brightnessChanged.connect(
                brightnessSlider.setValue)

            contrastSlider = QSlider(Qt.Horizontal)
            contrastSlider.setRange(-100, 100)
            contrastSlider.setValue(self.videoWidget.contrast())
            contrastSlider.sliderMoved.connect(self.videoWidget.setContrast)
            self.videoWidget.contrastChanged.connect(contrastSlider.setValue)

            hueSlider = QSlider(Qt.Horizontal)
            hueSlider.setRange(-100, 100)
            hueSlider.setValue(self.videoWidget.hue())
            hueSlider.sliderMoved.connect(self.videoWidget.setHue)
            self.videoWidget.hueChanged.connect(hueSlider.setValue)

            saturationSlider = QSlider(Qt.Horizontal)
            saturationSlider.setRange(-100, 100)
            saturationSlider.setValue(self.videoWidget.saturation())
            saturationSlider.sliderMoved.connect(
                self.videoWidget.setSaturation)
            self.videoWidget.saturationChanged.connect(
                saturationSlider.setValue)

            layout = QFormLayout()
            layout.addRow("Brightness", brightnessSlider)
            layout.addRow("Contrast", contrastSlider)
            layout.addRow("Hue", hueSlider)
            layout.addRow("Saturation", saturationSlider)

            button = QPushButton("Close")
            layout.addRow(button)

            self.colorDialog = QDialog(self)
            self.colorDialog.setWindowTitle("Color Options")
            self.colorDialog.setLayout(layout)

            button.clicked.connect(self.colorDialog.close)

        self.colorDialog.show()


if __name__ == '__main__':
    import sys
    appctxt = ApplicationContext()       # 1. Instantiate ApplicationContext
    #app = QApplication(sys.argv)

    player = Player(sys.argv[1:])
    # player.show()
    player.showMaximized()
    exit_code = appctxt.app.exec_()      # 2. Invoke appctxt.app.exec_()
    sys.exit(exit_code)

