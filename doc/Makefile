# This makefile is used for converting the POD documents for Moosic into various
# output formats, such as the manpage format. This requires GNU make, the
# "install" utility program, python, and the pod2man and pod2html utilities (the
# latter two are usually included with Perl).

VERSION=1.5.6
PROGRAMS=moosic moosicd
STATIC_DOCS=../README.txt ../License.txt ../ChangeLog ../NEWS \
    Todo History Moosic_API.txt moosic_hackers.txt
MANPAGES_1:=$(PROGRAMS:=.1)
MANPAGES_3:=Moosic_API.3
HTMLDOCS:=$(PROGRAMS:=.html) Moosic_API.html

.PHONY: all
all: $(MANPAGES_1) $(MANPAGES_3) $(HTMLDOCS)
	-

Moosic_API.pod: Moosic_API.intro.pod Moosic_API.sect0.pod Moosic_API.sect1.pod Moosic_API.sect2.pod Moosic_API.sect3.pod Moosic_API.sect4.pod Moosic_API.sect5.pod Moosic_API.sect6.pod
	cat $^ > $@

%.txt: %.pod
	pod2text -l $< $@

%.1: %.pod
	pod2man --section 1 --release "Moosic ${VERSION}" --center "" $< $@

%.3: %.pod
	pod2man --section 3 --release "Moosic ${VERSION}" --center "" $< $@

%.html: %.pod
	pod2html --podpath=. --htmlroot=. --infile=$< --outfile=$@
	rm -f pod2htm*

#.PHONY: install
#install: all
#	install -d $(INSTALL_PREFIX)
#	install -d $(INSTALL_PREFIX)/share/man/man1
#	install -m 644 $(MANPAGES_1) $(INSTALL_PREFIX)/share/man/man1/
#	install -d $(INSTALL_PREFIX)/share/man/man3
#	install -m 644 $(MANPAGES_3) $(INSTALL_PREFIX)/share/man/man3/
#	install -d $(INSTALL_PREFIX)/share/doc/moosic
#	install -m 644 $(STATIC_DOCS) $(PYTHON_MODULES) $(INSTALL_PREFIX)/share/doc/moosic/
#	install -d $(INSTALL_PREFIX)/share/doc/moosic/html
#	install -m 644 $(HTMLDOCS) $(INSTALL_PREFIX)/share/doc/moosic/html/

.PHONY: clean
clean:
	rm -f $(MANPAGES_1) $(MANPAGES_3) $(HTMLDOCS)
