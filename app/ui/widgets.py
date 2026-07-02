from PySide6 import QtCore, QtGui, QtWidgets

from ..constants import group_color as _group_color
from ..theme import THEME_MGR
from ..ui import icons as _icons

# svg_icons merged into ui.icons — unified draw() dispatches automatically
_svg_icons = _icons


def _mix_colors(c1: QtGui.QColor, c2: QtGui.QColor, t: float) -> QtGui.QColor:
    t = max(0.0, min(1.0, t))
    return QtGui.QColor(
        int(c1.red()   * (1 - t) + c2.red()   * t),
        int(c1.green() * (1 - t) + c2.green() * t),
        int(c1.blue()  * (1 - t) + c2.blue()  * t),
    )


class _HoverMixin:
    """Tracks hover state via WA_Hover events. Call _init_hover() in __init__."""

    _hover: bool

    def _init_hover(self):
        self._hover = False
        self.setAttribute(QtCore.Qt.WA_Hover)

    def event(self, e):
        t = e.type()
        if t == QtCore.QEvent.HoverEnter:
            self._hover = True
            self.update()
        elif t == QtCore.QEvent.HoverLeave:
            self._hover = False
            self.update()
        return super().event(e)


class ThumbnailActionButton(_HoverMixin, QtWidgets.QAbstractButton):
    """Small circular overlay button on a thumbnail card (e.g. rotate icon)."""

    def __init__(self, icon_name: str, color: str = "#8E8E93", size: int = 24,
                 bg_alpha: float = 0.62, parent=None):
        super().__init__(parent)
        self._icon_name = icon_name
        self._color     = QtGui.QColor(color)
        self._bg_alpha  = bg_alpha
        self._press     = False
        self.setFixedSize(size, size)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self._init_hover()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._press = True
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._press = False
        self.update()
        super().mouseReleaseEvent(event)
        event.accept()   # prevent propagation to DraggableCard underneath

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r  = self.rect().adjusted(1, 1, -1, -1)
        cx = self.width()  / 2.0
        cy = self.height() / 2.0

        bg_a = 0.88 if self._press else (0.80 if self._hover else self._bg_alpha)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(14, 16, 24, int(bg_a * 255)))
        p.drawEllipse(r)

        bc = QtGui.QColor(self._color)
        bc.setAlphaF(0.90 if self._hover else 0.60)
        p.setPen(QtGui.QPen(bc, 1.5))
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawEllipse(r)

        icon_sz = self.width() * 0.56
        icon_rf = QtCore.QRectF(cx - icon_sz/2, cy - icon_sz/2, icon_sz, icon_sz)
        ic = QtGui.QColor(self._color)
        ic.setAlphaF(1.0)
        if _svg_icons.has_svg(self._icon_name):
            _svg_icons.draw(p, icon_rf, self._icon_name, ic)
        else:
            _icons.draw(p, icon_rf, self._icon_name, ic)
        p.end()


class GroupDeck(QtWidgets.QWidget):
    """Анімована стопка карток для згорнутої групи.
    При hover карточки розсуваються по діагоналі — суто декоративно, клік
    по колоді нічого не робить (розгортання лише через іконку групи внизу).
    Під колодою — QLineEdit для кастомної назви вихідного файлу."""

    MAX_SHADOW = 3
    SO         = 5     # base stacking offset px
    TOP_PAD    = 22    # vertical room above top card for upward hover movement

    def __init__(self, group_num, pixmaps, default_name, screen,
                 thumb_w, thumb_h, cell_w, parent=None):
        super().__init__(parent)
        self._group_num  = group_num
        self._screen     = screen
        self._thumb_w    = thumb_w
        self._thumb_h    = thumb_h
        self._pixmap     = pixmaps[-1] if pixmaps else None
        self._page_count = len(pixmaps)
        self._spread     = 0.0
        self._color      = _group_color(group_num)

        n_shadow = min(max(len(pixmaps) - 1, 0), self.MAX_SHADOW)
        SO, TP   = self.SO, self.TOP_PAD

        self._rest_tx = [
            ((n_shadow - i) * float(SO), (n_shadow - i) * float(SO))
            for i in range(n_shadow)
        ]
        _D   = 10.0
        _lag = [0.75, 0.45, 0.10]
        self._spread_tx = [
            (
                (n_shadow - i) * SO + _D * (1.0 - _lag[(n_shadow - i) - 1]),
                (n_shadow - i) * SO + _D * (1.0 - _lag[(n_shadow - i) - 1]),
            )
            for i in range(n_shadow)
        ]

        self._anim = QtCore.QVariantAnimation(self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim_value)

        self._x_center = (cell_w - thumb_w) // 2
        name_y         = TP + thumb_h + self.MAX_SHADOW * SO + 8
        total_h        = name_y + 18 + 6
        self.setFixedSize(cell_w, total_h)
        self.setAttribute(QtCore.Qt.WA_Hover)

        color = self._color
        self._name_edit = QtWidgets.QLineEdit(default_name, self)
        self._name_edit.setFixedSize(thumb_w, 18)
        self._name_edit.move(self._x_center, name_y)
        self._name_edit.setAlignment(QtCore.Qt.AlignCenter)
        self._name_edit.setPlaceholderText("назва файлу")
        self._name_edit.setCursorPosition(0)
        self._name_edit.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 3px;
                color: rgba(255,255,255,0.38);
                font-size: 10px;
                padding: 0 2px;
                selection-background-color: {color};
            }}
            QLineEdit:hover {{
                color: rgba(255,255,255,0.68);
                border-color: rgba(255,255,255,0.22);
                background: rgba(255,255,255,0.05);
            }}
            QLineEdit:focus {{
                background: #21232c;
                border-color: {color};
                color: rgba(255,255,255,0.9);
            }}
        """)
        self._name_edit.editingFinished.connect(
            lambda: screen.set_group_name(group_num, self._name_edit.text())
        )

    def _on_anim_value(self, v):
        self._spread = float(v)
        self.update()

    def event(self, e):
        if e.type() == QtCore.QEvent.HoverEnter:
            self._anim.stop()
            self._anim.setStartValue(self._spread)
            self._anim.setEndValue(1.0)
            self._anim.start()
        elif e.type() == QtCore.QEvent.HoverLeave:
            self._anim.stop()
            self._anim.setStartValue(self._spread)
            self._anim.setEndValue(0.0)
            self._anim.start()
        return super().event(e)

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        s      = self._spread
        tw, th = self._thumb_w, self._thumb_h
        color  = QtGui.QColor(self._color)

        cx = self._x_center + tw / 2.0 - s * 10.0
        cy = self.TOP_PAD   + th / 2.0 - s * 10.0

        for i, (r0, r1) in enumerate(zip(self._rest_tx, self._spread_tx, strict=True)):
            dx = r0[0] + (r1[0] - r0[0]) * s
            dy = r0[1] + (r1[1] - r0[1]) * s
            card_x = cx + dx - tw / 2.0
            card_y = cy + dy - th / 2.0

            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor(0, 0, 0, 20))
            p.drawRoundedRect(QtCore.QRectF(card_x + 2, card_y + 4, tw, th), 5, 5)

            bc = QtGui.QColor(color)
            bc.setAlpha(100 + i * 40)
            p.setPen(QtGui.QPen(bc, 2.15))
            p.setBrush(QtCore.Qt.white)
            p.drawRoundedRect(QtCore.QRectF(card_x, card_y, tw, th), 5, 5)

        p.save()
        p.translate(cx, cy)
        p.rotate(-s * 2.0)
        p.translate(-tw / 2.0, -th / 2.0)

        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(0, 0, 0, 55))
        p.drawRoundedRect(QtCore.QRectF(1, 4, tw, th), 5, 5)

        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtCore.Qt.white)
        p.drawRoundedRect(QtCore.QRectF(0, 0, tw, th), 5, 5)

        if self._pixmap:
            inner = QtCore.QRectF(2, 2, tw - 4, th - 4)
            clip  = QtGui.QPainterPath()
            clip.addRoundedRect(inner, 4.0, 4.0)
            p.save()
            p.setClipPath(clip)
            p.drawPixmap(inner.toAlignedRect(), self._pixmap)
            p.restore()

        pen_out = QtGui.QPen(color, 3.8)
        pen_out.setJoinStyle(QtCore.Qt.RoundJoin)
        p.setPen(pen_out)
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawRoundedRect(QtCore.QRectF(0, 0, tw, th), 5, 5)

        echo = QtGui.QColor(color)
        echo.setAlphaF(0.65)
        pen_in = QtGui.QPen(echo, 2.0)
        pen_in.setJoinStyle(QtCore.Qt.RoundJoin)
        p.setPen(pen_in)
        p.drawRoundedRect(QtCore.QRectF(3, 3, tw - 6, th - 6), 2, 2)

        _bs = 42
        _bx = (tw - _bs) / 2.0
        _by = (th - _bs) / 2.0
        _br = QtCore.QRectF(_bx + 3, _by + 3, _bs - 6, _bs - 6)
        _bc = QtGui.QColor(color)
        _bc.setAlpha(160)
        p.setPen(QtGui.QPen(_bc, 1.6))
        p.setBrush(QtGui.QColor(30, 32, 42, 140))
        p.drawRoundedRect(_br, 7, 7)
        bf = QtGui.QFont()
        bf.setPixelSize(14)
        bf.setWeight(QtGui.QFont.Bold)
        p.setFont(bf)
        p.setPen(QtGui.QColor(255, 255, 255, 230))
        p.drawText(_br, QtCore.Qt.AlignCenter, str(self._group_num))

        cf = QtGui.QFont()
        cf.setPixelSize(10)
        cf.setWeight(QtGui.QFont.DemiBold)
        p.setFont(cf)
        p.setPen(QtGui.QColor(0, 0, 0, 130))
        p.drawText(
            QtCore.QRectF(0, th - 20, tw, 16),
            QtCore.Qt.AlignCenter,
            f"{self._page_count} стор."
        )

        p.restore()
        p.end()


class FullBorderPaper(QtWidgets.QWidget):
    """Карточка сторінки: білий фон + мініатюра + кольорова рамка.
    color=None → тонка сіра рамка (непризначена сторінка)."""

    def __init__(self, thumb_w, thumb_h, color=None, pixmap=None, parent=None):
        super().__init__(parent)
        self._color  = QtGui.QColor(color) if color else None
        self._pixmap = pixmap
        self.setFixedSize(thumb_w, thumb_h)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h, r = float(self.width()), float(self.height()), 5.0

        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(255, 255, 255))
        p.drawRoundedRect(QtCore.QRectF(0, 0, w, h), r, r)

        if self._pixmap:
            inner = QtCore.QRectF(2, 2, w - 4, h - 4)
            clip  = QtGui.QPainterPath()
            clip.addRoundedRect(inner, 4.0, 4.0)
            p.save()
            p.setClipPath(clip)
            iw, ih   = int(inner.width()), int(inner.height())
            scaled   = self._pixmap.scaled(iw, ih, QtCore.Qt.KeepAspectRatio,
                                           QtCore.Qt.SmoothTransformation)
            xo = inner.x() + (iw - scaled.width())  / 2
            yo = inner.y() + (ih - scaled.height()) / 2
            p.drawPixmap(int(xo), int(yo), scaled)
            p.restore()

        if not self._color:
            p.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 28), 1.0))
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawRoundedRect(QtCore.QRectF(0.5, 0.5, w - 1, h - 1), r, r)
            p.end()
            return

        inset = 3.0
        ri    = max(r - inset, 1.5)

        pen_out = QtGui.QPen(self._color, 3.8)
        pen_out.setJoinStyle(QtCore.Qt.RoundJoin)
        p.setPen(pen_out)
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawRoundedRect(QtCore.QRectF(0, 0, w, h), r, r)

        echo = QtGui.QColor(self._color)
        echo.setAlphaF(0.65)
        pen_in = QtGui.QPen(echo, 2.0)
        pen_in.setJoinStyle(QtCore.Qt.RoundJoin)
        p.setPen(pen_in)
        p.drawRoundedRect(QtCore.QRectF(inset, inset, w - 2*inset, h - 2*inset), ri, ri)

        p.end()


class GroupButton(QtWidgets.QAbstractButton):
    """Маленька кнопка вибору активної групи (використовується як вибір і як оверлей)."""

    def __init__(self, num: int, color: str, bg_alpha: int = 255, parent=None):
        super().__init__(parent)
        self._num      = num
        self._color    = QtGui.QColor(color)
        self._bg_alpha = bg_alpha
        self.setCheckable(True)
        self.setFixedSize(38, 38)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.NoFocus)

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = self.rect().adjusted(3, 3, -3, -3)

        if self.isChecked():
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(self._color)
            p.drawRoundedRect(r, 7, 7)
            p.setPen(QtGui.QColor(255, 255, 255, 230))
        else:
            bc = QtGui.QColor(self._color)
            bc.setAlpha(160)
            p.setPen(QtGui.QPen(bc, 1.6))
            p.setBrush(QtGui.QColor(30, 32, 42, self._bg_alpha))
            p.drawRoundedRect(r, 7, 7)
            p.setPen(QtGui.QColor(255, 255, 255, 230) if self._bg_alpha < 255
                     else self._color)

        f = QtGui.QFont()
        f.setPixelSize(14)
        f.setWeight(QtGui.QFont.Bold)
        p.setFont(f)
        p.drawText(r, QtCore.Qt.AlignCenter, str(self._num))
        p.end()


class DraggableCard(QtWidgets.QFrame):
    """Картка мініатюри з drag-and-drop, кліком для призначення групи
    та ctrl+клік для збільшеного перегляду сторінки (лишається відкритим
    до кліку деінде — див. ScreenMergeMulti.begin_zoom_preview)."""

    def __init__(self, visual_idx: int, screen, parent=None):
        super().__init__(parent)
        self._visual_idx     = visual_idx
        self._screen         = screen
        self._drag_start     = None
        self._did_drag       = False
        self._ctrl_zoom_press = False   # this press/release cycle opened the preview
        self._thumb_w        = 0
        self._thumb_h        = 0
        self.setAcceptDrops(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setMouseTracking(True)

    def set_thumb_size(self, thumb_w: int, thumb_h: int):
        """Розмір відображеної мініатюри — потрібен для розрахунку збільшеного прев'ю."""
        self._thumb_w = thumb_w
        self._thumb_h = thumb_h

    def _in_thumb_area(self, pos: QtCore.QPoint) -> bool:
        """True лише над самою мініатюрою (paper), не над інфо-смужкою з кнопками
        повороту/видалення під нею — там підказка ctrl+клік не потрібна."""
        return 0 <= pos.y() < self._thumb_h

    def enterEvent(self, event):
        if self._in_thumb_area(self.mapFromGlobal(QtGui.QCursor.pos())):
            self._screen.show_zoom_hint(QtGui.QCursor.pos())
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._screen.hide_zoom_hint()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if (event.button() == QtCore.Qt.LeftButton
                and event.modifiers() & QtCore.Qt.ControlModifier):
            self._ctrl_zoom_press = True
            self._screen.hide_zoom_hint()
            self._screen.begin_zoom_preview(
                self._visual_idx, self._thumb_w, self._thumb_h,
                self.mapToGlobal(event.pos()),
            )
            event.accept()
            return
        self._ctrl_zoom_press = False
        if event.button() == QtCore.Qt.LeftButton:
            self._drag_start = event.pos()
            self._did_drag   = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._ctrl_zoom_press:
            return
        if (self._drag_start is not None
                and event.buttons() & QtCore.Qt.LeftButton
                and (event.pos() - self._drag_start).manhattanLength() > 8):
            self._did_drag = True
            self._screen.hide_zoom_hint()
            self._do_drag(event.pos())
        elif not event.buttons():
            if self._in_thumb_area(event.pos()):
                self._screen.move_zoom_hint(self.mapToGlobal(event.pos()))
            else:
                self._screen.hide_zoom_hint()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._ctrl_zoom_press and event.button() == QtCore.Qt.LeftButton:
            # Preview stays open — closing it is handled globally by a click
            # outside its bounds (ScreenMergeMulti.eventFilter), not by release.
            self._ctrl_zoom_press = False
            if self._in_thumb_area(event.pos()):
                self._screen.show_zoom_hint(self.mapToGlobal(event.pos()))
            super().mouseReleaseEvent(event)
            return
        if event.button() == QtCore.Qt.LeftButton and not self._did_drag:
            self._screen.add_to_active_group(self._visual_idx)
        elif event.button() == QtCore.Qt.RightButton and not self._did_drag:
            self._screen.remove_from_group(self._visual_idx)
        self._drag_start = None
        self._did_drag   = False
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        event.accept()

    def _do_drag(self, pos):
        pix  = self.grab()
        semi = QtGui.QPixmap(pix.size())
        semi.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(semi)
        painter.setOpacity(0.72)
        painter.drawPixmap(0, 0, pix)
        painter.end()

        self._screen.start_drag(self._visual_idx, self)

        drag = QtGui.QDrag(self)
        mime = QtCore.QMimeData()
        mime.setText(str(self._visual_idx))
        drag.setMimeData(mime)
        drag.setPixmap(semi)
        drag.setHotSpot(self._drag_start or pos)
        self._drag_start = None
        drag.exec(QtCore.Qt.MoveAction)

        self._screen.end_drag()

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            self._screen.set_drop_indicator(self._visual_idx)
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            self._screen.set_drop_indicator(self._visual_idx)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._screen.set_drop_indicator(None)
        super().dragLeaveEvent(event)


class ZoomHintBubble(QtWidgets.QWidget):
    """Спливаюча підказка біля курсору: 'Ctrl + клік — збільшити мініатюру'.

    Малює фон/рамку/текст самостійно в paintEvent (як ZoomPreview), а не через
    QSS + WA_StyledBackground на дочірніх QLabel — той підхід ненадійно
    перемальовувався на translucent top-level вікні, яке move()-иться щокадру
    під час стеження за курсором, тож фон іноді просто не встигав намалюватись
    і лишався сам світлий текст просто над мініатюрою."""

    _KEY  = "Ctrl"
    _TEXT = "+ клік — збільшити"
    _PAD_X, _PAD_Y, _GAP = 10, 7, 6

    def __init__(self):
        super().__init__(None, QtCore.Qt.ToolTip | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        self._key_font  = _icons.sf_font(10, QtGui.QFont.Bold)
        self._text_font = _icons.sf_font(11, QtGui.QFont.DemiBold)

        fm_key  = QtGui.QFontMetrics(self._key_font)
        fm_text = QtGui.QFontMetrics(self._text_font)
        self._key_rect = fm_key.boundingRect(self._KEY).adjusted(-6, -3, 6, 3)
        text_w  = fm_text.horizontalAdvance(self._TEXT)
        row_h   = max(self._key_rect.height(), fm_text.height())

        w = self._PAD_X + self._key_rect.width() + self._GAP + text_w + self._PAD_X
        h = row_h + self._PAD_Y * 2
        self.resize(w, h)

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        t = THEME_MGR.get()

        # Same palette as the right sidebar (bg_sidebar/bg_border) so the hint
        # reads as part of the app, not a one-off popup with its own colors.
        bg = QtGui.QColor(t.bg_sidebar)
        bg.setAlpha(248)
        border = QtGui.QColor(t.bg_border)
        border.setAlpha(255)
        p.setPen(QtGui.QPen(border, 1.2))
        p.setBrush(bg)
        p.drawRoundedRect(rect, 8.0, 8.0)

        label_color = QtGui.QColor(t.nav_label_active_color)

        cy = self.height() / 2.0
        key_r = QtCore.QRectF(self._PAD_X, cy - self._key_rect.height() / 2.0,
                              self._key_rect.width(), self._key_rect.height())
        p.setPen(QtCore.Qt.NoPen)
        key_fill = QtGui.QColor(label_color)
        key_fill.setAlpha(28)
        p.setBrush(key_fill)
        p.drawRoundedRect(key_r, 4.0, 4.0)
        key_border = QtGui.QColor(label_color)
        key_border.setAlpha(70)
        p.setPen(QtGui.QPen(key_border, 1.0))
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawRoundedRect(key_r, 4.0, 4.0)

        key_text = QtGui.QColor(label_color)
        key_text.setAlpha(t.nav_label_active_alpha)
        p.setFont(self._key_font)
        p.setPen(key_text)
        p.drawText(key_r, QtCore.Qt.AlignCenter, self._KEY)

        text_r = QtCore.QRectF(key_r.right() + self._GAP, 0,
                               self.width() - key_r.right() - self._GAP - self._PAD_X,
                               self.height())
        text_color = QtGui.QColor(label_color)
        text_color.setAlpha(t.nav_label_active_alpha)
        p.setFont(self._text_font)
        p.setPen(text_color)
        p.drawText(text_r, QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, self._TEXT)
        p.end()

    _OFFSET = 18, 20

    def show_near(self, global_pos: QtCore.QPoint):
        ox, oy = self._OFFSET
        x, y = global_pos.x() + ox, global_pos.y() + oy
        screen = QtGui.QGuiApplication.screenAt(global_pos) or QtGui.QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            # Flip to the opposite side of the cursor when the default placement
            # would push the bubble past the screen edge — plain clamping keeps
            # the cursor-relative offset, so near a corner the cursor (and its
            # OS pointer icon) ends up sitting on top of part of the text instead
            # of beside it. Flipping keeps the whole phrase clear of the cursor.
            if x + self.width() > geo.right():
                x = global_pos.x() - ox - self.width()
            if y + self.height() > geo.bottom():
                y = global_pos.y() - oy - self.height()
            x = max(geo.left(), min(x, geo.right()  - self.width()))
            y = max(geo.top(),  min(y, geo.bottom() - self.height()))
        self.move(x, y)
        self.show()
        self.raise_()


class ZoomPreview(QtWidgets.QWidget):
    """Спливаюче збільшене прев'ю сторінки — показується під час утримання
    ctrl+ліва кнопка миші на мініатюрі.

    Caller creates a fresh instance per show and discards it on hide/close —
    a same-size, same-position re-show of a translucent top-level
    (WA_TranslucentBackground + Qt.ToolTip) window does not reliably get its
    Windows layered-window compositor surface refreshed by
    update()/repaint()/hide()+show() alone on a reused instance, since most
    pages in a document share the same dimensions."""

    def __init__(self):
        super().__init__(None, QtCore.Qt.ToolTip | QtCore.Qt.FramelessWindowHint)
        self.setObjectName("zoom_preview")
        # NOT transparent for mouse events: a click landing on the preview
        # must be swallowed here (see mousePressEvent) rather than falling
        # through to whatever thumbnail/widget happens to sit underneath it —
        # clicking the preview itself should never trigger an action there.
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self._pixmap = None

        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 8)
        shadow.setColor(QtGui.QColor(0, 0, 0, 160))
        self.setGraphicsEffect(shadow)

    def mousePressEvent(self, event):
        # Clicking the preview keeps it open — only a click elsewhere closes
        # it (ScreenMergeMulti's global event filter).
        event.accept()

    def show_pixmap(self, pixmap: QtGui.QPixmap, target_w: int, target_h: int,
                     global_pos: QtCore.QPoint):
        self._pixmap = pixmap.scaled(
            target_w, target_h, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
        )
        self.resize(self._pixmap.size())
        self.move_near(global_pos)
        self.show()
        self.raise_()

    def move_near(self, global_pos: QtCore.QPoint):
        x = global_pos.x() - self.width()  // 2
        y = global_pos.y() - self.height() // 2
        screen = QtGui.QGuiApplication.screenAt(global_pos) or QtGui.QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = max(geo.left() + 8, min(x, geo.right()  - self.width()  - 8))
            y = max(geo.top()  + 8, min(y, geo.bottom() - self.height() - 8))
        self.move(x, y)

    def paintEvent(self, event):
        if not self._pixmap:
            return
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = QtCore.QRectF(self.rect())
        clip = QtGui.QPainterPath()
        clip.addRoundedRect(rect, 8.0, 8.0)
        p.setClipPath(clip)
        p.drawPixmap(self.rect(), self._pixmap)
        p.setClipping(False)
        p.setPen(QtGui.QPen(QtGui.QColor(120, 140, 255, 200), 2.0))
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8.0, 8.0)
        p.end()

    def dropEvent(self, event):
        if event.mimeData().hasText():
            src = int(event.mimeData().text())
            dst = self._visual_idx
            self._screen.set_drop_indicator(None)
            if src != dst:
                self._screen.reorder_pages(src, dst)
            event.acceptProposedAction()
