rm -f iaas/*.rpm && \
./admin/build-package --distribution fedora-20 $(pwd) && \
mv *.rpm iaas && \
export VERSION=$(python -c "import flocker, admin.release; print '-'.join(admin.release.make_rpm_version(flocker.__version__))") && \
cd iaas && \
vagrant provision && \
cd ..
