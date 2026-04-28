import json

# 要注意系统变量和环境变量之间的冲突，如果某个环境变量的值是系统变量赋予的，那么这个时候优先设置系统变量（如果这时候直接修改环境变量可能会造成冲突）
# 如果某个环境变量没有和系统变量做关联，那么直接修改环境变量即可

def map_env_signal(signals: list, channel_conf_path: str) -> dict:
    with open(channel_conf_path, 'r', encoding='utf-8') as f:
        channel_data = json.load(f)
        channel_data = channel_data["canoe"]["dbc_files"]

    if not channel_data:
        raise ValueError("请添加CAN的DBC文件，并正确配置CAN通道映射")

    # print(channel_data)
        
    mapped_signals = {}

    for sig in signals:
        sig_type=sig.split('::')[0]
        if sig_type.lower()!='env':
            continue
        can_channel=sig.split('::')[1] # 获取can通道号
        can_msg=sig.split('::')[2] # 获取can报文名
        can_node=can_msg.split('_')[0] # 获取can节点
        sig=sig.split('::')[-1]
        
        if can_channel in channel_data:
            if sig not in mapped_signals:
                env="E_"+channel_data[can_channel]["short_name"]+"_"+can_node+"_"+can_msg+"_"+sig+"_Pv"
                mapped_signals[sig]='::'.join([sig_type, env])

        # if can_channel=="CAN 1" and control_data.get(sig):
        #     if sig not in mapped_signals:
        #         ms=control_data[sig]
        #         ms['env'] = '::'.join([sig_type, ms['env']])
        #         mapped_signals[sig]=ms['env']
        # elif can_channel=="CAN 2" and chassis_data.get(sig):
        #     if sig not in mapped_signals:
        #         ms=chassis_data[sig]
        #         ms['env'] = '::'.join([sig_type, ms['env']])
        #         mapped_signals[sig]=ms['env']
        else:
            raise ValueError(f"在任何已导入的DBC文件中都没有发现信号 '{sig}' .")
        
    return mapped_signals
