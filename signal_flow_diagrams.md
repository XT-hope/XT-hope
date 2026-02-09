# 信号流程控制可视化图表

## 1. 整体架构图

```mermaid
graph TB
    subgraph 输入层
        A[信号名称] 
        B[信号值]
        C[时间参数]
        D[检测条件]
        E[异步配置]
    end
    
    subgraph 核心控制层
        F[信号控制器<br/>Signal Controller]
        G[时间管理器<br/>Time Manager]
        H[信号检测器<br/>Signal Checker]
        I[异步执行器<br/>Async Executor]
    end
    
    subgraph 功能模块层
        J[Set Signal<br/>设置信号]
        K[Check Signal<br/>检查信号]
        L[Wait<br/>等待延迟]
        M[Timeout<br/>超时控制]
        N[Duration<br/>持续检测]
        O[Async<br/>异步执行]
    end
    
    subgraph 输出层
        P[执行状态]
        Q[信号结果]
        R[时间统计]
        S[错误信息]
    end
    
    A --> F
    B --> F
    C --> G
    D --> H
    E --> I
    
    F --> J
    F --> K
    G --> L
    G --> M
    G --> N
    I --> O
    
    J --> H
    K --> H
    L --> H
    M --> H
    N --> H
    O --> H
    
    H --> P
    H --> Q
    H --> R
    H --> S
```

## 2. 基础信号检测流程

```mermaid
flowchart TD
    Start([开始]) --> SetSignal[设置信号<br/>Set Signal]
    SetSignal --> HasWait{需要等待?}
    HasWait -->|是| Wait[等待延迟<br/>Wait]
    HasWait -->|否| CheckSignal
    Wait --> CheckSignal[检查信号<br/>Check Signal]
    
    CheckSignal --> TimeoutCheck{是否超时?}
    TimeoutCheck -->|是| TimeoutHandler[超时处理]
    TimeoutCheck -->|否| ConditionCheck{信号满足条件?}
    
    ConditionCheck -->|是| Success[成功]
    ConditionCheck -->|否| Retry{是否重试?}
    Retry -->|是| CheckSignal
    Retry -->|否| Fail[失败]
    
    TimeoutHandler --> End([结束])
    Success --> End
    Fail --> End
    
    style SetSignal fill:#90EE90
    style CheckSignal fill:#87CEEB
    style Wait fill:#FFD700
    style Success fill:#32CD32
    style Fail fill:#DC143C
    style TimeoutHandler fill:#FF6347
```

## 3. 持续检测流程（Duration）

```mermaid
flowchart TD
    Start([开始持续检测]) --> Init[初始化参数<br/>设置Duration时间]
    Init --> StartTimer[启动计时器]
    StartTimer --> LoopStart[循环开始]
    
    LoopStart --> CheckSignal[检查信号状态]
    CheckSignal --> RecordResult[记录检测结果]
    RecordResult --> CheckTime{持续时间到?}
    
    CheckTime -->|否| WaitInterval[等待检测间隔]
    WaitInterval --> LoopStart
    
    CheckTime -->|是| Analyze[分析汇总结果]
    Analyze --> CalcStats[计算统计数据<br/>成功率/失败率]
    CalcStats --> Output[输出结果]
    Output --> End([结束])
    
    style Init fill:#90EE90
    style CheckSignal fill:#87CEEB
    style RecordResult fill:#DDA0DD
    style Analyze fill:#FFA500
    style Output fill:#32CD32
```

## 4. 异步并行执行流程（Async）

```mermaid
flowchart TD
    Start([主流程开始]) --> CreateTasks[创建异步任务组]
    
    CreateTasks --> Task1[任务1<br/>设置信号A]
    CreateTasks --> Task2[任务2<br/>设置信号B]
    CreateTasks --> Task3[任务3<br/>等待延迟]
    
    Task1 --> Check1[检查信号A]
    Task2 --> Check2[检查信号B]
    Task3 --> Check3[检查信号C]
    
    Check1 --> Result1[结果1]
    Check2 --> Result2[结果2]
    Check3 --> Result3[结果3]
    
    Result1 --> WaitAll[等待所有任务完成]
    Result2 --> WaitAll
    Result3 --> WaitAll
    
    WaitAll --> GlobalTimeout{全局超时?}
    GlobalTimeout -->|是| TimeoutResult[超时返回]
    GlobalTimeout -->|否| CollectResults[汇总所有结果]
    
    CollectResults --> AnalyzeResults{分析结果}
    AnalyzeResults -->|全部成功| AllSuccess[所有任务成功]
    AnalyzeResults -->|部分失败| PartialFail[部分任务失败]
    AnalyzeResults -->|全部失败| AllFail[所有任务失败]
    
    TimeoutResult --> End([结束])
    AllSuccess --> End
    PartialFail --> End
    AllFail --> End
    
    style CreateTasks fill:#90EE90
    style Task1 fill:#87CEEB
    style Task2 fill:#87CEEB
    style Task3 fill:#87CEEB
    style AllSuccess fill:#32CD32
    style PartialFail fill:#FFA500
    style AllFail fill:#DC143C
    style TimeoutResult fill:#FF6347
```

## 5. 带超时的信号检测详细流程

```mermaid
flowchart TD
    Start([开始]) --> SetSignal[设置信号<br/>signal = value]
    SetSignal --> StartTimeout[启动超时计时器<br/>timeout = T秒]
    StartTimeout --> LoopCheck[循环检查信号]
    
    LoopCheck --> ReadSignal[读取当前信号值]
    ReadSignal --> EvalCondition{信号满足条件?}
    
    EvalCondition -->|是| StopTimer[停止计时器]
    StopTimer --> CalcTime[计算实际用时]
    CalcTime --> SuccessReturn[返回成功结果]
    SuccessReturn --> End([结束])
    
    EvalCondition -->|否| CheckTimeout{是否超时?}
    CheckTimeout -->|是| TimeoutHandler[超时处理]
    TimeoutHandler --> LogTimeout[记录超时日志]
    LogTimeout --> TimeoutReturn[返回超时结果]
    TimeoutReturn --> End
    
    CheckTimeout -->|否| ShortWait[短暂等待<br/>避免CPU占用]
    ShortWait --> LoopCheck
    
    style SetSignal fill:#90EE90
    style StartTimeout fill:#FFD700
    style ReadSignal fill:#87CEEB
    style SuccessReturn fill:#32CD32
    style TimeoutHandler fill:#FF6347
    style ShortWait fill:#DDA0DD
```

## 6. 状态机图

```mermaid
stateDiagram-v2
    [*] --> 空闲
    空闲 --> 准备中: 接收任务
    准备中 --> 信号已设置: 执行Set Signal
    信号已设置 --> 检测中: 开始检测
    
    检测中 --> 检测中: 未满足条件且未超时<br/>(持续检测/重试)
    检测中 --> 完成: 检测成功
    检测中 --> 失败: 检测失败<br/>(超过重试次数)
    检测中 --> 超时失败: 超时
    
    完成 --> 空闲: 重置
    失败 --> 空闲: 重置
    超时失败 --> 空闲: 重置
    
    note right of 检测中
        在此状态下:
        - 执行Check Signal
        - 监控Timeout
        - 处理Duration
    end note
```

## 7. 组件交互时序图

```mermaid
sequenceDiagram
    participant U as 用户/调用者
    participant SC as 信号控制器
    participant TM as 时间管理器
    participant CK as 信号检测器
    participant AE as 异步执行器
    
    U->>SC: 1. 设置信号(name, value)
    SC-->>U: 设置成功
    
    U->>TM: 2. 启动超时计时(timeout)
    TM-->>U: 计时器已启动
    
    U->>CK: 3. 检查信号(condition)
    
    loop 每次检查
        CK->>SC: 读取信号值
        SC-->>CK: 返回当前值
        CK->>TM: 查询是否超时
        TM-->>CK: 未超时
        CK->>CK: 评估条件
    end
    
    alt 条件满足
        CK-->>U: 返回成功
    else 超时
        TM->>CK: 超时通知
        CK-->>U: 返回超时
    end
    
    Note over U,AE: 异步场景
    U->>AE: 4. 创建异步任务组
    
    par 并行执行
        AE->>SC: 任务1: 设置信号A
        AE->>CK: 任务1: 检查信号A
    and
        AE->>SC: 任务2: 设置信号B
        AE->>CK: 任务2: 检查信号B
    and
        AE->>TM: 任务3: 等待
        AE->>CK: 任务3: 检查信号C
    end
    
    AE->>AE: 汇总所有结果
    AE-->>U: 返回综合结果
```

## 8. 数据流图

```mermaid
flowchart LR
    subgraph Input[输入数据]
        I1[信号名称]
        I2[信号值]
        I3[时间参数]
        I4[检测条件]
        I5[配置参数]
    end
    
    subgraph Processing[处理层]
        P1[信号存储]
        P2[时间控制]
        P3[条件评估]
        P4[并发管理]
    end
    
    subgraph Output[输出数据]
        O1[状态码]
        O2[信号结果]
        O3[执行时长]
        O4[错误详情]
        O5[统计数据]
    end
    
    I1 --> P1
    I2 --> P1
    I3 --> P2
    I4 --> P3
    I5 --> P4
    
    P1 --> P3
    P2 --> P3
    P4 --> P3
    
    P3 --> O1
    P3 --> O2
    P2 --> O3
    P3 --> O4
    P3 --> O5
    
    style Input fill:#E6F3FF
    style Processing fill:#FFF4E6
    style Output fill:#E8F5E9
```

## 9. 错误处理流程

```mermaid
flowchart TD
    Start([任何操作执行]) --> TryCatch{捕获异常?}
    
    TryCatch -->|无异常| NormalExec[正常执行]
    TryCatch -->|有异常| ErrorType{错误类型}
    
    ErrorType -->|信号不存在| E1[错误码: SIGNAL_NOT_FOUND]
    ErrorType -->|超时| E2[错误码: TIMEOUT]
    ErrorType -->|检测失败| E3[错误码: CHECK_FAILED]
    ErrorType -->|异步任务异常| E4[错误码: ASYNC_ERROR]
    ErrorType -->|其他| E5[错误码: UNKNOWN_ERROR]
    
    E1 --> Log[记录错误日志]
    E2 --> Log
    E3 --> Log
    E4 --> Log
    E5 --> Log
    
    Log --> Strategy{错误处理策略}
    Strategy -->|重试| RetryCheck{重试次数<最大值?}
    Strategy -->|退出| Return[返回错误结果]
    Strategy -->|忽略| Continue[继续执行]
    
    RetryCheck -->|是| RetryWait[等待重试间隔]
    RetryCheck -->|否| Return
    RetryWait --> Start
    
    NormalExec --> End([结束])
    Return --> End
    Continue --> End
    
    style ErrorType fill:#FFB6C1
    style E1 fill:#DC143C,color:#fff
    style E2 fill:#DC143C,color:#fff
    style E3 fill:#DC143C,color:#fff
    style E4 fill:#DC143C,color:#fff
    style E5 fill:#DC143C,color:#fff
    style Log fill:#FFA500
    style Return fill:#FF6347
```

## 10. 典型应用示例：设备就绪检测

```mermaid
flowchart TD
    Start([开始设备初始化]) --> PowerOn[设备上电]
    PowerOn --> SetSignal[设置信号: device_ready = False]
    SetSignal --> Wait[等待设备初始化<br/>Wait 2秒]
    
    Wait --> StartCheck[开始检查设备状态]
    StartCheck --> SetTimeout[设置超时: 10秒]
    SetTimeout --> LoopCheck[循环检查]
    
    LoopCheck --> ReadStatus[读取 device_ready 信号]
    ReadStatus --> CheckReady{device_ready == True?}
    
    CheckReady -->|是| DeviceReady[设备就绪]
    DeviceReady --> LogSuccess[记录成功日志]
    LogSuccess --> StartApp[启动应用程序]
    StartApp --> End([结束 - 成功])
    
    CheckReady -->|否| CheckTimeout{是否超时?}
    CheckTimeout -->|是| TimeoutHandle[超时处理]
    TimeoutHandle --> LogError[记录错误: 设备初始化超时]
    LogError --> Retry{是否重试?}
    Retry -->|是| PowerOff[设备断电]
    PowerOff --> WaitCool[等待5秒]
    WaitCool --> PowerOn
    Retry -->|否| Failed([结束 - 失败])
    
    CheckTimeout -->|否| WaitShort[等待100ms]
    WaitShort --> LoopCheck
    
    style SetSignal fill:#90EE90
    style Wait fill:#FFD700
    style DeviceReady fill:#32CD32
    style TimeoutHandle fill:#FF6347
    style Failed fill:#DC143C,color:#fff
```

## 使用说明

这些图表使用Mermaid语法编写，可以在以下环境中查看：
1. GitHub/GitLab的Markdown文件中直接渲染
2. VS Code安装Mermaid插件
3. 在线工具：https://mermaid.live/
4. 其他支持Mermaid的Markdown编辑器

每个图表展示了不同的架构视角和应用场景，您可以根据实际需求选择合适的模式进行实现。
