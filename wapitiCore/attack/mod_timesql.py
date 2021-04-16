#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# This file is part of the Wapiti project (https://wapiti.sourceforge.io)
# Copyright (C) 2008-2021 Nicolas Surribas
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
from requests.exceptions import ReadTimeout, RequestException

from wapitiCore.attack.attack import Attack
from wapitiCore.language.vulnerability import Messages, HIGH_LEVEL, CRITICAL_LEVEL, _
from wapitiCore.definitions.blindsql import NAME
from wapitiCore.net.web import Request


class mod_timesql(Attack):
    """
    Detect SQL injection vulnerabilities using blind time-based technique.
    """

    PAYLOADS_FILE = "blindSQLPayloads.txt"
    time_to_sleep = 6
    name = "timesql"
    PRIORITY = 6

    MSG_VULN = _("Blind SQL vulnerability")

    def __init__(self, crawler, persister, logger, attack_options):
        Attack.__init__(self, crawler, persister, logger, attack_options)
        self.mutator = self.get_mutator()

    def set_timeout(self, timeout):
        self.time_to_sleep = str(1 + int(timeout))

    async def attack(self, request: Request):
        page = request.path
        saw_internal_error = False
        current_parameter = None
        vulnerable_parameter = False

        for mutated_request, parameter, _payload, _flags in self.mutator.mutate(request):
            if current_parameter != parameter:
                # Forget what we know about current parameter
                current_parameter = parameter
                vulnerable_parameter = False
            elif vulnerable_parameter:
                # If parameter is vulnerable, just skip till next parameter
                continue

            if self.verbose == 2:
                print("[¨] {0}".format(mutated_request))

            try:
                response = await self.crawler.async_send(mutated_request)
            except ReadTimeout:
                # The request with time based payload did timeout, what about a regular request?
                if self.does_timeout(request):
                    self.network_errors += 1
                    print("[!] Too much lag from website, can't reliably test time-based blind SQL")
                    break

                if parameter == "QUERY_STRING":
                    vuln_message = Messages.MSG_QS_INJECT.format(self.MSG_VULN, page)
                    log_message = Messages.MSG_QS_INJECT
                else:
                    vuln_message = _("{0} via injection in the parameter {1}").format(self.MSG_VULN, parameter)
                    log_message = Messages.MSG_PARAM_INJECT

                self.add_vuln(
                    request_id=request.path_id,
                    category=NAME,
                    level=CRITICAL_LEVEL,
                    request=mutated_request,
                    info=vuln_message,
                    parameter=parameter
                )

                self.log_red("---")
                self.log_red(
                    log_message,
                    self.MSG_VULN,
                    page,
                    parameter
                )
                self.log_red(Messages.MSG_EVIL_REQUEST)
                self.log_red(mutated_request.http_repr())
                self.log_red("---")

                # We reached maximum exploitation for this parameter, don't send more payloads
                vulnerable_parameter = True
                continue
            except RequestException:
                self.network_errors += 1
                continue
            else:
                if response.status == 500 and not saw_internal_error:
                    saw_internal_error = True
                    if parameter == "QUERY_STRING":
                        anom_msg = Messages.MSG_QS_500
                    else:
                        anom_msg = Messages.MSG_PARAM_500.format(parameter)

                    self.add_anom(
                        request_id=request.path_id,
                        category=Messages.ERROR_500,
                        level=HIGH_LEVEL,
                        request=mutated_request,
                        info=anom_msg,
                        parameter=parameter
                    )

                    self.log_orange("---")
                    self.log_orange(Messages.MSG_500, page)
                    self.log_orange(Messages.MSG_EVIL_REQUEST)
                    self.log_orange(mutated_request.http_repr())
                    self.log_orange("---")
