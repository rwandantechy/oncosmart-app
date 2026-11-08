# Every target is defined once, in the workspace Makefile one directory up.
# This only forwards, so `make api` works from either directory.
.PHONY: all
all:
	@$(MAKE) -C .. $(MAKECMDGOALS)

%:
	@$(MAKE) -C .. $@
