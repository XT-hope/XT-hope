# Qt6 悬浮可移动 AI 提示按钮

这是一个完整的 Qt6 悬浮按钮实现示例，可用于创建 AI 助手、快捷工具等场景。

## 功能特性

1. **无边框悬浮窗口** - 使用 `Qt::FramelessWindowHint` 实现
2. **始终置顶** - 使用 `Qt::WindowStaysOnTopHint` 保持窗口在最上层
3. **鼠标拖动** - 实现 `mousePressEvent`、`mouseMoveEvent`、`mouseReleaseEvent`
4. **美观的 UI** - 圆形按钮、渐变色、阴影效果
5. **两种版本** - 简单版和带展开菜单的高级版

## 实现方式

### 核心技术点

#### 1. 无边框置顶窗口

```cpp
// C++ 版本
setWindowFlags(Qt::FramelessWindowHint | Qt::WindowStaysOnTopHint | Qt::Tool);
setAttribute(Qt::WA_TranslucentBackground);
```

```python
# Python 版本
self.setWindowFlags(
    Qt.WindowType.FramelessWindowHint | 
    Qt.WindowType.WindowStaysOnTopHint | 
    Qt.WindowType.Tool
)
self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
```

**窗口标志说明：**
- `FramelessWindowHint` - 无边框窗口
- `WindowStaysOnTopHint` - 窗口置顶
- `Tool` - 工具窗口（不在任务栏显示）
- `WA_TranslucentBackground` - 透明背景

#### 2. 鼠标拖动实现

```cpp
// C++ 版本
void mousePressEvent(QMouseEvent *event) override {
    if (event->button() == Qt::LeftButton) {
        dragging = true;
        dragPosition = event->pos();
    }
}

void mouseMoveEvent(QMouseEvent *event) override {
    if (dragging) {
        move(event->globalPosition().toPoint() - dragPosition);
    }
}

void mouseReleaseEvent(QMouseEvent *event) override {
    if (event->button() == Qt::LeftButton) {
        dragging = false;
    }
}
```

#### 3. 圆形渐变按钮样式

```css
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #667eea, stop:1 #764ba2);
    color: white;
    border-radius: 30px;  /* 圆形效果 */
    font-size: 18px;
    font-weight: bold;
    border: 3px solid white;
}
```

## 使用方法

### Python (PyQt6) 版本

#### 1. 安装依赖

```bash
pip install PyQt6
```

#### 2. 运行示例

```bash
python qt6_floating_button_example.py
```

#### 3. 代码示例

```python
from PyQt6.QtWidgets import QApplication
import sys

# 简单版本
app = QApplication(sys.argv)
button = FloatingButton()
button.show()
sys.exit(app.exec())

# 高级版本（带展开菜单）
app = QApplication(sys.argv)
button = AdvancedFloatingButton()
button.show()
sys.exit(app.exec())
```

### C++ (Qt6) 版本

#### 1. 使用 CMake 编译（推荐）

```bash
mkdir build
cd build
cmake ..
make
./bin/FloatingAIButton
```

#### 2. 使用 qmake 编译

```bash
qmake qt6_floating_button.pro
make
./bin/FloatingAIButton
```

#### 3. 集成到现有项目

```cpp
#include <QApplication>

int main(int argc, char *argv[]) {
    QApplication app(argc, argv);
    
    FloatingButton floatingButton;
    floatingButton.show();
    
    return app.exec();
}
```

## 两个版本对比

### 1. 简单版 (`FloatingButton`)

- 单个悬浮按钮
- 点击显示 AI 对话框
- 适合简单场景

### 2. 高级版 (`AdvancedFloatingButton`)

- 可展开/收起的菜单
- 多个功能按钮（对话、代码、帮助）
- 不同颜色区分功能
- 适合复杂场景

## 自定义配置

### 修改按钮大小

```python
self.main_button.setFixedSize(80, 80)  # 修改为 80x80
```

### 修改初始位置

```python
# 左上角
self.move(20, 20)

# 右上角
screen = QApplication.primaryScreen().geometry()
self.move(screen.width() - 100, 20)

# 屏幕中心
screen = QApplication.primaryScreen().geometry()
self.move((screen.width() - self.width()) // 2, 
          (screen.height() - self.height()) // 2)
```

### 修改颜色主题

```python
# 修改渐变色
background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
    stop:0 #FF6B6B, stop:1 #4ECDC4);  # 红蓝渐变
```

### 添加图标

```python
from PyQt6.QtGui import QIcon

self.main_button.setIcon(QIcon('path/to/icon.png'))
self.main_button.setIconSize(QSize(40, 40))
```

## 高级功能扩展

### 1. 添加右键菜单

```python
from PyQt6.QtWidgets import QMenu

def contextMenuEvent(self, event):
    menu = QMenu(self)
    
    settings_action = menu.addAction("设置")
    about_action = menu.addAction("关于")
    quit_action = menu.addAction("退出")
    
    action = menu.exec(event.globalPos())
    
    if action == quit_action:
        QApplication.quit()
```

### 2. 添加动画效果

```python
from PyQt6.QtCore import QPropertyAnimation, QEasingCurve

def add_animation(self):
    self.animation = QPropertyAnimation(self, b"pos")
    self.animation.setDuration(300)
    self.animation.setEasingCurve(QEasingCurve.Type.OutBounce)
```

### 3. 添加系统托盘

```python
from PyQt6.QtWidgets import QSystemTrayIcon

tray_icon = QSystemTrayIcon(QIcon('icon.png'), app)
tray_icon.setToolTip('AI 助手')
tray_icon.show()
```

### 4. 集成 AI API

```python
import requests

def send_to_ai(self, message):
    # OpenAI API 示例
    response = requests.post(
        'https://api.openai.com/v1/chat/completions',
        headers={'Authorization': f'Bearer {API_KEY}'},
        json={
            'model': 'gpt-4',
            'messages': [{'role': 'user', 'content': message}]
        }
    )
    return response.json()
```

### 5. 保存窗口位置

```python
from PyQt6.QtCore import QSettings

# 保存位置
def closeEvent(self, event):
    settings = QSettings('MyCompany', 'FloatingButton')
    settings.setValue('position', self.pos())
    event.accept()

# 恢复位置
def __init__(self):
    super().__init__()
    settings = QSettings('MyCompany', 'FloatingButton')
    if settings.contains('position'):
        self.move(settings.value('position'))
```

## 常见问题

### Q1: 按钮不能拖动？
确保正确实现了 `mousePressEvent`、`mouseMoveEvent` 和 `mouseReleaseEvent` 三个事件。

### Q2: 窗口没有置顶？
检查是否设置了 `Qt::WindowStaysOnTopHint` 标志。

### Q3: 窗口有白色背景？
需要设置 `Qt::WA_TranslucentBackground` 属性。

### Q4: 在任务栏显示？
添加 `Qt::Tool` 窗口标志可以隐藏任务栏图标。

### Q5: 如何实现吸附边缘效果？

```python
def mouseReleaseEvent(self, event):
    if event.button() == Qt.MouseButton.LeftButton:
        self.dragging = False
        # 吸附到边缘
        screen = QApplication.primaryScreen().geometry()
        if self.x() < 50:
            self.move(0, self.y())
        elif self.x() > screen.width() - self.width() - 50:
            self.move(screen.width() - self.width(), self.y())
```

## 完整类图

```
FloatingButton (简单版)
├── QPushButton (主按钮)
└── AIPromptDialog (AI 对话框)
    ├── QLabel (标题)
    ├── QTextEdit (输入框)
    └── QPushButton (发送/取消按钮)

AdvancedFloatingButton (高级版)
├── QPushButton (主按钮)
├── QPushButton (对话按钮)
├── QPushButton (代码按钮)
├── QPushButton (帮助按钮)
└── AIPromptDialog (AI 对话框)
```

## 性能优化建议

1. **避免频繁重绘** - 使用 `update()` 而不是 `repaint()`
2. **使用样式表缓存** - 预定义样式字符串
3. **延迟加载对话框** - 点击时才创建对话框实例
4. **限制拖动频率** - 使用定时器限制移动事件处理频率

## 许可证

本示例代码可自由使用、修改和分发。

## 参考资料

- [Qt6 官方文档](https://doc.qt.io/qt-6/)
- [Qt Window Flags](https://doc.qt.io/qt-6/qt.html#WindowType-enum)
- [Qt Style Sheets](https://doc.qt.io/qt-6/stylesheet.html)
- [PyQt6 Documentation](https://www.riverbankcomputing.com/static/Docs/PyQt6/)
