import React, { useEffect, useState } from "react";
import {
    Table,
    TableCell,
    TableBody,
    TableHead,
    TableRow,
    Button,
    View,
    ScrollView,
    Flex,
} from "@aws-amplify/ui-react";
import { FiMail, FiRefreshCw } from "react-icons/fi";
import { useNavigate, useParams } from "react-router-dom";
import { get, del } from 'aws-amplify/api';
import moment from "moment";
import { Cache } from 'aws-amplify/utils';
import { LuMousePointerClick } from "react-icons/lu";
import { MdDeleteForever } from "react-icons/md";

const EmailMessages = () => {
    const cacheExpirationDuration = 5 * 60 * 1000; // 5 minutes
    const [messages, setMessages] = useState<any[]>([]);
    const [error, setError] = useState<unknown>(null);
    const [loading, setLoading] = useState(false);
    const navigate = useNavigate();
    const params = useParams();
    const emailAddress = params.addressId;

    const handleBackClick = () => {
        navigate(`/email-accounts/`);
    };

    async function handleDeleteAddress(emailAddress) {
        try {
            setLoading(true)
            const restOperation = del({
                apiName: 'disposible',
                path: `addresses/${emailAddress}/`,
            });
            await restOperation.response;
            console.log('DELETE call succeeded');
            handleBackClick();
        } catch (err) {
            console.error('DELETE call failed: ', err);
            setError(err);
        } finally {
            setLoading(false)
        }
    }

    async function handleDeleteMessage(event, emailAddress, messageId) {
        event.preventDefault();
        event.stopPropagation();
        try {
            setLoading(true)
            const restOperation = del({
                apiName: 'disposible',
                path: `addresses/${emailAddress}/${messageId}`,
            });
            await restOperation.response;

            // Remove the deleted message from the local state
            setMessages((prevMessages) => prevMessages.filter(message => message.messageId !== messageId));

            console.log('DELETE call succeeded');
        } catch (err) {
            console.error('DELETE call failed: ', err);
            setError(err);
        } finally {
            setLoading(false)
        }
    }

    async function getMessages(emailAddress: string, useCache = false) {
        setLoading(true);
        const cacheKey = `messagesCache_${emailAddress}`; // Unique cache key per email address

        try {
            // Check cache first
            if (useCache) {
                const cachedData = await Cache.getItem(cacheKey);
                if (cachedData) {
                    setMessages(cachedData);
                    setLoading(false);
                    return;
                }
            }

            // Fetch data from API if not cached or cache is bypassed
            const restOperation = get({
                apiName: 'disposible',
                path: `addresses/${emailAddress}`,
            });
            const { body } = await restOperation.response;
            const response = await body.json();

            if (Array.isArray(response)) {
                setMessages(response);
                // Cache the data
                Cache.setItem(cacheKey, response, { expires: new Date().getTime() + cacheExpirationDuration });
            }
        } catch (err) {
            console.error('GET call failed: ', err);
            setError(err);
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        getMessages(emailAddress); // Call the function to fetch addresses
    }, [emailAddress]);

    const handleMessageClick = (emailAddress, messageId) => {
        navigate(`/email-accounts/${encodeURIComponent(emailAddress)}/${messageId}`);
    };

    if (loading) return <div>Loading...</div>;
    if (error) return <div>Error fetching messages</div>;

    return (
        <>
            <Flex className="header-flex">
                <div className="email-header">
                    <h2>Email Messages: {emailAddress}</h2>
                </div>
            </Flex>
            <Flex justifyContent="flex-start" alignItems="center">
                <Button variation="destructive" onClick={() => handleDeleteAddress(emailAddress)} size="small">Delete</Button>
                <Button onClick={() => getMessages(emailAddress, false)} variation="primary">
                    <FiRefreshCw />
                </Button>
                <div style={{ flex: 1 }}></div> {/* Spacer element */}
                <Button onClick={() => handleBackClick()} justifyContent="flex-end" size="small">Back</Button>
            </Flex>
            <br />
            <br />
            <View
                backgroundColor="var(--amplify-colors-white)"
                borderRadius="6px"
                maxWidth="100%"
                padding="1rem"
                minHeight="50vh"
            >
                <br />
                <ScrollView>
                    <Table size="small" highlightOnHover={true} className="responsive-table">
                        <TableHead>
                            <TableRow>
                                <TableCell>From</TableCell>
                                <TableCell>Subject</TableCell>
                                <TableCell>Date</TableCell>
                                <TableCell>Actions</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {messages.map((item, index) => {
                                return (
                                    <TableRow onClick={() => handleMessageClick(emailAddress, item.messageId)} key={index}>
                                        <TableCell className="responsive-cell" data-label="From">
                                            {!item.is_read && <FiMail />}&nbsp;{item.commonHeaders.sender || item.commonHeaders.returnPath}
                                        </TableCell>
                                        <TableCell className="responsive-cell" data-label="Subject">{item.commonHeaders.subject}</TableCell>
                                        <TableCell className="responsive-cell" data-label="Date">{moment(item.commonHeaders.date).calendar()}</TableCell>
                                        <TableCell className="responsive-cell" data-label="Action">
                                            <Flex justifyContent="flex-start" alignItems="center" gap="small">
                                                <Button size="small" colorTheme="error" onClick={(event) => handleDeleteMessage(event, emailAddress, item.messageId)}>
                                                    <MdDeleteForever />&nbsp;Delete
                                                </Button>
                                                <Button size="small" onClick={() => handleMessageClick(emailAddress, item.messageId)}>
                                                    <LuMousePointerClick />&nbsp;Select
                                                </Button>
                                            </Flex>
                                        </TableCell>
                                    </TableRow>
                                );
                            })}
                        </TableBody>
                    </Table>
                </ScrollView>
            </View>
        </>
    );
};

export default EmailMessages;
