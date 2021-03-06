import uuid
import logging
from dataloader import logging as log
from dataloader import DataLoader, LoadSession
from dataloader.helper import incache, free, fastuuid

pvs = LoadSession(__name__)   # 定义Load Session
logger = log.getLogger(__name__)


class Config(object):
    """ 配置类，目前支持如下三个配置项 """
    DATABASE_URL = "postgresql://postgres:postgres@k8s-dev-1-localhost:32100/cpl_service?connect_timeout=2"

    # 多少条记录做一次IO提交到DB，默认 5W
    FLUSH_BUFF_SIZE = 10 * 10000

    # 每个批次生成多少条记录, 这个值影响占用内存的大小，默认10W
    ITER_CHUNK_SIZE = 20 * 10000

    LOG_LEVEL = logging.INFO
    SAVE_LOG_TO_FILE = True
    LOG_FILE_LOCATION = "/tmp"


# 2. Define LoadSession
cs = LoadSession(__name__)


# 2. Define LoadSession
@cs.regist_for("cpl_service")
def load_cpl_service_data():
    """ 1kw complex_lms_device and 1kw cpl_file"""
    from target.cpl_service import (
        ComplexLmsDevice,
        iter_complex_lms_device,
        iter_complex_group_association
    )

    for cplx in iter_complex_lms_device(
        100*10000, retaining=True,
        # 如果是UUID字段，请明确指定使用fastuuid()覆盖默认生成策略来提升性能
        complex_uuid=fastuuid(), device_uuid=fastuuid()
    ):
        yield cplx

    for grp in iter_complex_group_association(
        100*10000, group_uuid=fastuuid(),
        complex_uuid=incache(ComplexLmsDevice, 'complex_uuid')
    ):
        yield grp

    free(ComplexLmsDevice)


# 3. Create DataLoader App
app = DataLoader(__name__, Config)

# 4. Register LoadSession to DataLoader
app.register_session(cs)


# 5. Run the DataLoader app with app.run()
if __name__ == "__main__":
    app.run()
