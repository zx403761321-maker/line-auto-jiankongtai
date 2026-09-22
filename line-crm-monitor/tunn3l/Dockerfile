# tunn3l = pkg 打包的 Node 单二进制（依赖 glibc，python:3.12-slim 自带）
# 复用 api 的基础镜像（部署机已存在，避免再拉 debian 镜像超时）
# 二进制 98MB 不进包/git，由部署方 COPY 进 build context：
#   cp ~/.tunn3l/bin/tunn3l ./tunn3l/tunn3l
FROM python:3.12-slim
COPY tunn3l /usr/local/bin/tunn3l
RUN chmod +x /usr/local/bin/tunn3l
ENTRYPOINT ["tunn3l"]
