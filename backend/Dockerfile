FROM mcr.microsoft.com/dotnet/aspnet:8.0

COPY ./backend/platform /opt/virtocommerce/platform
COPY ./backend/YamlDotNet.dll /opt/virtocommerce/platform/app_data/modules

RUN apt-get update && apt-get install -y wget fontconfig libfreetype6 libx11-6 libxcb1 libxext6 libxrender1 xfonts-75dpi xfonts-base libjpeg62-turbo \
  && wget http://http.us.debian.org/debian/pool/main/o/openssl/libssl3_3.0.11-1~deb12u2_amd64.deb \
  && dpkg -i libssl3_3.0.11-1~deb12u2_amd64.deb \
  && wget https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3/wkhtmltox_0.12.6.1-3.bookworm_amd64.deb \
  && dpkg -i wkhtmltox_0.12.6.1-3.bookworm_amd64.deb

RUN apt-get clean autoclean \
    && apt-get autoremove --yes \
    && rm -rf /var/lib/{apt,dpkg,cache,log}/

WORKDIR /opt/virtocommerce/platform
EXPOSE 80
ENV ASPNETCORE_HTTP_PORTS=80
ENTRYPOINT ["dotnet", "VirtoCommerce.Platform.Web.dll"]  
