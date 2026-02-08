/*
 * Qt6 C++ 版本悬浮可移动 AI 提示按钮示例
 * 
 * 编译命令：
 * qmake && make
 * 或者使用 CMake（推荐）
 * 
 * 功能特性：
 * 1. 无边框悬浮窗口
 * 2. 鼠标拖动移动
 * 3. 窗口始终置顶
 * 4. 点击显示 AI 提示对话框
 */

#include <QApplication>
#include <QWidget>
#include <QPushButton>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QDialog>
#include <QLabel>
#include <QTextEdit>
#include <QMouseEvent>
#include <QScreen>

// AI 提示对话框类
class AIPromptDialog : public QDialog
{
    Q_OBJECT

public:
    explicit AIPromptDialog(QWidget *parent = nullptr) : QDialog(parent)
    {
        setWindowTitle("AI 助手");
        setMinimumSize(400, 300);
        
        // 创建主布局
        QVBoxLayout *mainLayout = new QVBoxLayout(this);
        
        // 标题
        QLabel *title = new QLabel("AI 智能助手", this);
        title->setStyleSheet(
            "QLabel {"
            "    font-size: 20px;"
            "    font-weight: bold;"
            "    color: #667eea;"
            "    padding: 10px;"
            "}"
        );
        mainLayout->addWidget(title);
        
        // 提示信息
        QLabel *infoLabel = new QLabel("请输入您的问题或需要帮助的内容：", this);
        infoLabel->setStyleSheet("padding: 5px;");
        mainLayout->addWidget(infoLabel);
        
        // 输入框
        inputText = new QTextEdit(this);
        inputText->setPlaceholderText("例如：帮我优化这段代码...");
        inputText->setStyleSheet(
            "QTextEdit {"
            "    border: 2px solid #e0e0e0;"
            "    border-radius: 5px;"
            "    padding: 10px;"
            "    font-size: 14px;"
            "}"
            "QTextEdit:focus {"
            "    border: 2px solid #667eea;"
            "}"
        );
        mainLayout->addWidget(inputText);
        
        // 按钮布局
        QHBoxLayout *buttonLayout = new QHBoxLayout();
        
        // 取消按钮
        QPushButton *cancelButton = new QPushButton("取消", this);
        cancelButton->setStyleSheet(
            "QPushButton {"
            "    background-color: #e0e0e0;"
            "    color: #333;"
            "    border: none;"
            "    border-radius: 5px;"
            "    padding: 10px 30px;"
            "    font-size: 14px;"
            "}"
            "QPushButton:hover {"
            "    background-color: #d0d0d0;"
            "}"
        );
        connect(cancelButton, &QPushButton::clicked, this, &QDialog::reject);
        
        // 发送按钮
        QPushButton *sendButton = new QPushButton("发送", this);
        sendButton->setStyleSheet(
            "QPushButton {"
            "    background-color: #667eea;"
            "    color: white;"
            "    border: none;"
            "    border-radius: 5px;"
            "    padding: 10px 30px;"
            "    font-size: 14px;"
            "    font-weight: bold;"
            "}"
            "QPushButton:hover {"
            "    background-color: #5568d3;"
            "}"
        );
        connect(sendButton, &QPushButton::clicked, this, &AIPromptDialog::sendMessage);
        
        buttonLayout->addStretch();
        buttonLayout->addWidget(cancelButton);
        buttonLayout->addWidget(sendButton);
        
        mainLayout->addLayout(buttonLayout);
    }

private slots:
    void sendMessage()
    {
        QString message = inputText->toPlainText();
        if (!message.trimmed().isEmpty()) {
            // 这里可以添加实际的 AI API 调用
            qDebug() << "发送给 AI:" << message;
            accept();
        } else {
            inputText->setFocus();
        }
    }

private:
    QTextEdit *inputText;
};

// 悬浮按钮类
class FloatingButton : public QWidget
{
    Q_OBJECT

public:
    explicit FloatingButton(QWidget *parent = nullptr) : QWidget(parent), dragging(false)
    {
        // 设置窗口属性：无边框、置顶、工具窗口
        setWindowFlags(Qt::FramelessWindowHint | Qt::WindowStaysOnTopHint | Qt::Tool);
        // 设置透明背景
        setAttribute(Qt::WA_TranslucentBackground);
        
        // 创建主按钮
        mainButton = new QPushButton("AI", this);
        mainButton->setFixedSize(60, 60);
        
        // 设置按钮样式 - 圆形渐变效果
        mainButton->setStyleSheet(
            "QPushButton {"
            "    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            "        stop:0 #667eea, stop:1 #764ba2);"
            "    color: white;"
            "    border-radius: 30px;"
            "    font-size: 18px;"
            "    font-weight: bold;"
            "    border: 3px solid white;"
            "}"
            "QPushButton:hover {"
            "    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            "        stop:0 #764ba2, stop:1 #667eea);"
            "}"
            "QPushButton:pressed {"
            "    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            "        stop:0 #5568d3, stop:1 #6a3f92);"
            "}"
        );
        
        connect(mainButton, &QPushButton::clicked, this, &FloatingButton::showAIDialog);
        
        // 布局
        QVBoxLayout *layout = new QVBoxLayout(this);
        layout->addWidget(mainButton);
        layout->setContentsMargins(5, 5, 5, 5);
        
        // 设置窗口大小
        resize(70, 70);
        
        // 设置初始位置（屏幕右下角）
        QScreen *screen = QApplication::primaryScreen();
        QRect screenGeometry = screen->geometry();
        move(screenGeometry.width() - 100, screenGeometry.height() - 150);
    }

protected:
    // 鼠标按下事件
    void mousePressEvent(QMouseEvent *event) override
    {
        if (event->button() == Qt::LeftButton) {
            dragging = true;
            dragPosition = event->pos();
        }
    }
    
    // 鼠标移动事件
    void mouseMoveEvent(QMouseEvent *event) override
    {
        if (dragging) {
            // 计算新位置并移动窗口
            move(event->globalPosition().toPoint() - dragPosition);
        }
    }
    
    // 鼠标释放事件
    void mouseReleaseEvent(QMouseEvent *event) override
    {
        if (event->button() == Qt::LeftButton) {
            dragging = false;
        }
    }

private slots:
    void showAIDialog()
    {
        AIPromptDialog dialog(this);
        dialog.exec();
    }

private:
    QPushButton *mainButton;
    bool dragging;
    QPoint dragPosition;
};

// 主函数
int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    
    FloatingButton floatingButton;
    floatingButton.show();
    
    return app.exec();
}

#include "qt6_floating_button_cpp_example.moc"
