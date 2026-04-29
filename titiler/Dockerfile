# TiTiler with custom colormaps.
# Thin wrapper around the official image — only adds Kenya-specific colormaps.

FROM ghcr.io/developmentseed/titiler:latest

# Copy custom colormap JSON files into the TiTiler colormap directory
COPY custom_colormaps/ /tmp/colormaps/

# TiTiler picks up JSON files from TITILER_API_COLORMAP_DIRECTORY at startup
ENV TITILER_API_COLORMAP_DIRECTORY=/tmp/colormaps

EXPOSE 8080
